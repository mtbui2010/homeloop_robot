"""Profile validator: ``python -m homeloop_robot.profiles validate [--strict]`` (docs/profiles.md).

Numbered rules, each printed with PASS / FAIL. Exit 0 only if every rule passes; ``--strict`` also
fails on warnings. The output ends with the count and the list of assumed parameters (never an error).
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from ..types import FailureCode
from . import (KINDS, PARAM_REGISTRY, PROB_KINDS, ROLES, load_real_fragments, load_spec)

DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"
CALIBRATION_MD = DOCS_DIR / "calibration.md"

SOURCE_RE = re.compile(r"^(https?://\S+|doi:10\.\S+|arXiv:\d{4}\.\d{4,5})$")
_URL_RE = re.compile(r"(https?://[^\s)<>\]\"'`]+|doi:10\.[^\s)<>\]\"'`]+|arXiv:\d{4}\.\d{4,5})", re.I)
NOISE_ROLES = ("failure", "user_noise", "safety_noise")


def norm_source(s: str) -> str:
    """Normalised source key: arXiv ids from abs/, pdf/ and arXiv: forms; DOIs lower-cased; other
    URLs as written (trailing punctuation dropped)."""
    s = str(s).strip().rstrip(".,;:")
    m = re.search(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})", s, re.I) or re.match(r"arxiv:(\d{4}\.\d{4,5})", s, re.I)
    if m:
        return f"arxiv:{m.group(1)}"
    m = re.search(r"(?:doi\.org/|^doi:)(10\.\S+)", s, re.I)
    if m:
        return f"doi:{m.group(1).lower()}"
    return s


def sources_in_text(text: str) -> set:
    return {norm_source(m) for m in _URL_RE.findall(text or "")}


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def check_value(name: str, e: dict) -> list:
    """Type-check one entry's value against its kind."""
    k, v = e.get("kind"), e.get("value")
    errs = []
    reg = PARAM_REGISTRY.get(name, {})
    keys = reg.get("keys") or e.get("keys")

    def prob(x, where):
        if not _num(x) or not (0.0 <= x <= 1.0):
            errs.append(f"{where}: {x!r} is not a probability in [0, 1]")

    if k == "prob":
        prob(v, name)
    elif k in ("prob_map", "map", "split", "categorical"):
        if not isinstance(v, dict) or not v:
            return [f"{name}: {k} value must be a non-empty mapping"]
        if keys and sorted(v) != sorted(keys):
            errs.append(f"{name}: keys {sorted(v)} != declared {sorted(keys)}")
        if k in ("prob_map", "split", "categorical"):
            for kk, x in v.items():
                prob(x, f"{name}.{kk}")
        if k in ("split", "categorical") and all(_num(x) for x in v.values()):
            if abs(sum(v.values()) - 1.0) > 1e-6:
                errs.append(f"{name}: {k} values sum to {sum(v.values())} != 1")
        if k == "split":
            for kk in v:
                try:
                    FailureCode(kk)
                except ValueError:
                    errs.append(f"{name}: split key {kk!r} is not a FailureCode")
    elif k in ("range_s", "range"):
        if not (isinstance(v, (list, tuple)) and len(v) == 2 and all(_num(x) for x in v)) or v[0] > v[1]:
            errs.append(f"{name}: range must be [lo, hi] with lo <= hi, got {v!r}")
        elif k == "range_s" and (v[0] < 0 or v[1] <= 0):
            errs.append(f"{name}: durations must be > 0, got {v!r}")
    elif k in ("duration_s", "speed_mps", "accel_mps2", "mass_kg", "words_per_s"):
        if not _num(v) or v <= 0:
            errs.append(f"{name}: {k} must be > 0, got {v!r}")
    elif k in ("distance_m", "rate_per_h"):
        if not _num(v) or v < 0:
            errs.append(f"{name}: {k} must be >= 0, got {v!r}")
    elif k == "count":
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            errs.append(f"{name}: count must be an int >= 0, got {v!r}")
    elif k == "lognormal":
        if not isinstance(v, dict) or not _num(v.get("median")) or v["median"] <= 0 or not _num(v.get("sigma")) \
                or v["sigma"] < 0:
            errs.append(f"{name}: lognormal needs median > 0 and sigma >= 0")
    elif k == "normal":
        if not isinstance(v, dict) or not _num(v.get("mean")) or not _num(v.get("sd")) or v["sd"] < 0:
            errs.append(f"{name}: normal needs mean and sd >= 0")
    elif k == "flag":
        if not isinstance(v, bool):
            errs.append(f"{name}: flag must be true/false")
    return errs


def _is_zero(e: dict) -> bool:
    v = e.get("value")
    if e.get("kind") in ("prob", "rate_per_h"):
        return v == 0
    if e.get("kind") == "prob_map":
        return all(x == 0 for x in (v or {}).values())
    return True


def _recompute(real: dict, spec: dict, which: str) -> dict:
    """Independent re-implementation of the derivation (rule 5/6 cross-check)."""
    out = {k: e.get("value") for k, e in real.items()}
    if which == "ideal":
        for rule in spec.get("rules") or []:
            if "match" in rule:
                roles = set(rule["match"].get("role") or [])
                for k, e in real.items():
                    if e.get("role") in roles:
                        if e["kind"] in ("prob", "rate_per_h"):
                            out[k] = 0.0
                        elif e["kind"] == "prob_map":
                            out[k] = {kk: 0.0 for kk in e["value"]}
            elif rule.get("param") in out:
                out[rule["param"]] = rule.get("set")
        return out
    sc = spec.get("scaling") or {}
    f, cap = float(sc.get("failure_prob_factor", 1.0)), float(sc.get("cap", 1.0))
    for k, e in real.items():
        if e.get("role") != "failure":
            continue
        if e["kind"] == "prob":
            out[k] = min(cap, e["value"] * f)
        elif e["kind"] == "prob_map":
            out[k] = {kk: min(cap, x * f) for kk, x in e["value"].items()}
        elif e["kind"] == "rate_per_h":
            out[k] = e["value"] * f
    for k, ov in (spec.get("overrides") or {}).items():
        if k in out:
            out[k] = ov.get("value")
    return out


def _note_or_warn(msg: str, warnings: list, out) -> None:
    """A derivation rule for a parameter `real` does not hold is a warning, unless no registered
    parameter shares its family prefix (e.g. no `user.*` fragment installed yet): then it is info."""
    m = re.search(r"for ([\w.]+):", msg)
    fam = m.group(1).split(".")[0] + "." if m else None
    if fam and not any(k.startswith(fam) for k in PARAM_REGISTRY):
        out(f"INFO  {msg} (no {fam}* parameters registered)")
    else:
        warnings.append(msg)


def run(strict: bool = False, out=print) -> int:
    from . import load_profile
    fails = 0
    warnings = []
    results = []

    def rule(n, title, errs):
        nonlocal fails
        results.append((n, title, errs))
        out(f"{'PASS' if not errs else 'FAIL'}  rule {n}: {title}")
        for e in errs[:50]:
            out(f"        {e}")
        if len(errs) > 50:
            out(f"        ... {len(errs) - 50} more")
        if errs:
            fails += 1

    # rule 1
    errs = []
    try:
        real, _frags, dup = load_real_fragments()
        errs += dup
    except Exception as e:                          # noqa: BLE001 - report any load error
        real = {}
        errs.append(f"real does not load: {type(e).__name__}: {e}")
    missing = sorted(set(PARAM_REGISTRY) - set(real))
    extra = sorted(set(real) - set(PARAM_REGISTRY))
    errs += [f"registry parameter {k} missing in real" for k in missing]
    errs += [f"real parameter {k} not in PARAM_REGISTRY" for k in extra]
    rule(1, f"real loads, {len(real)} params, key set == PARAM_REGISTRY ({len(PARAM_REGISTRY)})", errs)

    # calibration sources
    cal_text = CALIBRATION_MD.read_text(encoding="utf-8") if CALIBRATION_MD.is_file() else ""
    cal_sources = sources_in_text(cal_text)

    # rule 2
    errs = []
    for k in sorted(real):
        e = real[k]
        for f in ("kind", "role", "value", "note"):
            if f not in e:
                errs.append(f"{k}: missing {f}")
        if e.get("kind") not in KINDS:
            errs.append(f"{k}: unknown kind {e.get('kind')!r}")
        if e.get("role") not in ROLES:
            errs.append(f"{k}: unknown role {e.get('role')!r}")
        reg = PARAM_REGISTRY.get(k)
        if reg and (reg["kind"] != e.get("kind") or reg["role"] != e.get("role")):
            errs.append(f"{k}: kind/role {e.get('kind')}/{e.get('role')} != registry {reg['kind']}/{reg['role']}")
        if len(str(e.get("note") or "")) < 20:
            errs.append(f"{k}: note shorter than 20 characters")
        if "value" in e:
            errs += check_value(k, e)
    rule(2, "every entry has kind, role, value, note (>= 20 chars); values type-check", errs)

    # rule 3
    errs = []
    used = set()
    for k in sorted(real):
        e = real[k]
        if e.get("assumed"):
            continue
        src = str(e.get("source") or "")
        if not SOURCE_RE.match(src):
            errs.append(f"{k}: source {src!r} is not a URL / doi:10.x / arXiv:NNNN.NNNNN")
            continue
        if not str(e.get("where") or "").strip():
            errs.append(f"{k}: sourced entry needs `where` (page / table / figure)")
        used.add(norm_source(src))
        if norm_source(src) not in cal_sources:
            errs.append(f"{k}: source {src} is not listed in docs/calibration.md")
    rule(3, "sourced entries: source URL, where, listed in docs/calibration.md", errs)

    # rule 4
    errs = []
    assumed = sorted(k for k, e in real.items() if e.get("assumed"))
    for k in assumed:
        e = real[k]
        if len(str(e.get("note") or "")) < 20:
            errs.append(f"{k}: assumed entry needs a note saying why")
        if e.get("anchor") is not None:
            a = str(e["anchor"])
            if not SOURCE_RE.match(a):
                errs.append(f"{k}: anchor {a!r} is not a URL / DOI / arXiv id")
            else:
                used.add(norm_source(a))
                if norm_source(a) not in cal_sources:
                    errs.append(f"{k}: anchor {a} is not listed in docs/calibration.md")
        if e.get("source") and not SOURCE_RE.match(str(e["source"])):
            errs.append(f"{k}: source {e['source']!r} is not a URL")
        elif e.get("source"):
            used.add(norm_source(e["source"]))
    rule(4, f"assumed entries have a note; anchors valid and listed ({len(assumed)} assumed)", errs)

    # rule 5
    errs = []
    try:
        ideal = load_profile("ideal")
        ispec = load_spec("ideal")
        if ispec.get("derive_from") != "real":
            errs.append("ideal: derive_from must be real")
        if set(ideal.params) != set(real):
            errs.append("ideal key set != real key set")
        for k in sorted(ideal.params):
            e = ideal.params[k]
            if e.get("role") in NOISE_ROLES and e.get("kind") in PROB_KINDS + ("rate_per_h",) and not _is_zero(e):
                errs.append(f"ideal: {k} = {e.get('value')!r} is not 0")
        if ideal.has("user.motion.rate_per_h") and ideal.get("user.motion.rate_per_h") != 0:
            errs.append("ideal: user.motion.rate_per_h must be 0")
        if ideal.has("pose.sigma_m") and ideal.get("pose.sigma_m") != 0:
            errs.append("ideal: pose.sigma_m must be 0")
        re_ideal = _recompute(real, ispec, "ideal")
        for k in sorted(real):
            if ideal.get(k) != re_ideal[k]:
                errs.append(f"ideal: {k} = {ideal.get(k)!r} != recomputed {re_ideal[k]!r}")
        for n in ideal.meta.get("notes") or []:
            _note_or_warn(f"ideal: {n}", warnings, out)
    except Exception as e:                          # noqa: BLE001
        errs.append(f"ideal does not load: {type(e).__name__}: {e}")
    rule(5, "ideal: every failure / noise probability is 0, people static, keys == real", errs)

    # rule 6
    errs = []
    try:
        stress = load_profile("stress")
        sspec = load_spec("stress")
        if sspec.get("derive_from") != "real":
            errs.append("stress: derive_from must be real")
        sc = sspec.get("scaling") or {}
        if len(str(sc.get("note") or "")) < 20:
            errs.append("stress: scaling needs a note")
        if not (sc.get("source") or sc.get("assumed") is True):
            errs.append("stress: scaling needs a source or assumed: true")
        for k, ov in sorted((sspec.get("overrides") or {}).items()):
            if "value" not in ov:
                errs.append(f"stress override {k}: no value")
            if len(str(ov.get("note") or "")) < 20:
                errs.append(f"stress override {k}: needs a note")
            if k not in real:
                errs.append(f"stress override {k}: not a real parameter")
            if ov.get("assumed") is True:
                continue
            src = str(ov.get("source") or "")
            if not SOURCE_RE.match(src):
                errs.append(f"stress override {k}: needs a source URL or assumed: true")
            else:
                used.add(norm_source(src))
                if norm_source(src) not in cal_sources:
                    errs.append(f"stress override {k}: source {src} not listed in docs/calibration.md")
                if not str(ov.get("where") or "").strip():
                    errs.append(f"stress override {k}: needs `where`")
            if k in real:
                chk = check_value(k, {**real[k], "value": ov.get("value")})
                errs += [f"stress override {x}" for x in chk]
        if set(stress.params) != set(real):
            errs.append("stress key set != real key set")
        re_stress = _recompute(real, sspec, "stress")
        for k in sorted(real):
            if stress.get(k) != re_stress[k]:
                errs.append(f"stress: {k} = {stress.get(k)!r} != recomputed {re_stress[k]!r}")
            e = stress.params[k]
            if e.get("kind") in PROB_KINDS:
                errs += [f"stress: {x}" for x in check_value(k, e)]
        for n in stress.meta.get("notes") or []:
            _note_or_warn(f"stress: {n}", warnings, out)
    except Exception as e:                          # noqa: BLE001
        errs.append(f"stress does not load: {type(e).__name__}: {e}")
    rule(6, "stress: derived from real by the documented scaling + sourced overrides", errs)

    # rule 7
    errs = []
    if not CALIBRATION_MD.is_file():
        errs.append(f"{CALIBRATION_MD} does not exist")
    else:
        other_docs = set()
        for p in sorted(DOCS_DIR.glob("*.md")):
            if p.name != "calibration.md":
                other_docs |= sources_in_text(p.read_text(encoding="utf-8"))
        # user / safety parameters may cite sources through docs blocks too: count every source any
        # profile fragment mentions anywhere (source, anchor, where, note)
        frag_text = "\n".join(p.read_text(encoding="utf-8")
                              for d in ("real", "ideal", "stress")
                              for p in sorted((Path(__file__).resolve().parent / d).glob("*.yaml")))
        mentioned = sources_in_text(frag_text)
        for s in sorted(cal_sources - used - other_docs - mentioned):
            warnings.append(f"docs/calibration.md lists {s}, which no parameter or doc uses")
    rule(7, f"docs/calibration.md exists and lists every source ({len(cal_sources)} distinct)", errs)

    for w in warnings:
        out(f"WARN  {w}")
    out(f"assumed: {len(assumed)} params")
    for k in assumed:
        out(f"  - {k}")
    n_fail = fails + (len(warnings) if strict else 0)
    out(f"== profiles validate{' --strict' if strict else ''}: {fails} rule(s) failed, {len(warnings)} warning(s)")
    return 1 if n_fail else 0
