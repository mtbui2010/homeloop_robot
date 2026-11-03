"""Profiles: ``ideal`` / ``real`` / ``stress`` parameter sets of the mock robot (docs/profiles.md).

``real`` holds the calibrated values in fragment files (``real/skills.yaml``, ``real/user.yaml``,
``real/safety.yaml``); ``ideal`` and ``stress`` hold only derivation rules applied to ``real``.
:data:`PARAM_REGISTRY` lists every parameter the code reads; the validator checks that ``real`` holds
exactly these.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json
from pathlib import Path

import yaml

PROFILE_DIR = Path(__file__).resolve().parent
PROFILES = ("ideal", "real", "stress")

PROB_KINDS = ("prob", "prob_map")
KINDS = ("prob", "prob_map", "split", "range_s", "range", "duration_s", "speed_mps", "accel_mps2", "distance_m",
         "mass_kg", "rate_per_h", "count", "lognormal", "normal", "categorical", "flag", "words_per_s", "value",
         "map")
ROLES = ("failure", "recovery", "nominal", "user_noise", "safety_noise")


def _p(kind, role, keys=None):
    d = {"kind": kind, "role": role}
    if keys is not None:
        d["keys"] = list(keys)
    return d


# Every parameter the code reads. robot-core owns the skills block; robot-human-safety owns the block
# between the user-safety markers.
PARAM_REGISTRY: dict = {
    # ── skills (robot-core) ────────────────────────────────────────────────────────────────────────────
    "hw.p_per_motion_call": _p("prob", "failure"),
    "hw.p_per_sensor_call": _p("prob", "failure"),
    "hw.p_persistent": _p("prob", "failure"),
    "estop.rate_per_h": _p("rate_per_h", "failure"),
    "move.p_fail": _p("prob_map", "failure", ["low", "medium", "high"]),
    "move.split": _p("split", "failure", ["blocked", "unreachable"]),
    "move.p_retry_clears_blocked": _p("prob", "recovery"),
    "move.p_help_clears_blocked": _p("prob", "recovery"),
    "move.p_stuck_retry_success": _p("prob", "recovery"),
    "move.p_false_arrival_hard": _p("prob", "failure"),
    "move.p_false_arrival_normal": _p("prob", "failure"),
    "move.false_arrival_offset_m": _p("distance_m", "nominal"),
    "move.speed_mps": _p("speed_mps", "nominal"),
    "move.timeout_s": _p("duration_s", "nominal"),
    "move.p_timeout": _p("prob", "failure"),
    "move.fail_time_frac": _p("range", "nominal"),
    "move.person_standoff_m": _p("distance_m", "nominal"),
    "perception.p_unavailable": _p("prob", "failure"),
    "perception.p_clear_on_wait": _p("prob", "recovery"),
    "find.p_miss": _p("prob", "failure"),
    "find.p_false_positive": _p("prob", "failure"),
    "find.p_wrong_instance": _p("prob_map", "failure", ["few", "many"]),
    "find.duration_s": _p("range_s", "nominal"),
    "look.duration_s": _p("range_s", "nominal"),
    "pick.p_fail": _p("prob_map", "failure", ["low", "medium", "high"]),
    "pick.p_fail_class": _p("prob_map", "failure", ["deformable", "light_deformable"]),
    "pick.split": _p("split", "failure", ["absent", "unreachable", "blocked", "grasp_failed"]),
    "pick.p_retry_success": _p("prob", "recovery"),
    "pick_place.duration_s": _p("range_s", "nominal"),
    "verify.p_false_success": _p("prob", "failure"),
    "carry.p_drop": _p("prob", "failure"),
    "carry.payload_kg": _p("mass_kg", "nominal"),
    "place.p_drop": _p("prob", "failure"),
    "handover.p_drop": _p("prob", "failure"),
    "handover.duration_s": _p("range_s", "nominal"),
    "open.p_fail": _p("prob_map", "failure", ["door", "drawer"]),
    "open.p_retry_success": _p("prob_map", "recovery", ["door", "drawer"]),
    "open.split": _p("split", "failure", ["blocked", "unreachable"]),
    "open.duration_s": _p("range_s", "nominal"),
    "close.p_fail": _p("prob_map", "failure", ["door", "drawer"]),
    "close.p_retry_success": _p("prob_map", "recovery", ["door", "drawer"]),
    "close.split": _p("split", "failure", ["blocked", "unreachable"]),
    "close.duration_s": _p("range_s", "nominal"),
    "vlm.p_false_yes": _p("prob", "failure"),
    "vlm.p_false_no": _p("prob", "failure"),
    "vlm.duration_s": _p("range_s", "nominal"),
    "grasp_check.p_wrong": _p("prob", "failure"),
    "grasp_check.duration_s": _p("duration_s", "nominal"),
    "pose.sigma_m": _p("distance_m", "failure"),
    "pose.duration_s": _p("duration_s", "nominal"),
    "say.words_per_s": _p("words_per_s", "nominal"),
    "ask.timeout_s": _p("duration_s", "nominal"),
    "dock.duration_s": _p("range_s", "nominal"),
    # BEGIN user-safety (robot-human-safety edits only inside this block)
    "asr.en.near_wer": _p("prob", "user_noise"),
    "asr.en.far_wer": _p("prob", "user_noise"),
    "asr.ko.near_cer": _p("prob", "user_noise"),
    "asr.ko.far_cer": _p("prob", "user_noise"),
    "asr.en.app_wer": _p("prob", "user_noise"),
    "asr.ko.app_cer": _p("prob", "user_noise"),
    "asr.p_not_heard": _p("prob", "user_noise"),
    "asr.p_partial": _p("prob", "user_noise"),
    "asr.far_threshold_m": _p("distance_m", "nominal"),
    "asr.op_shares": _p("categorical", "nominal", ['sub', 'del', 'ins']),
    "user.answer.p_wrong": _p("prob", "user_noise"),
    "user.answer.p_not_sure": _p("prob", "user_noise"),
    "user.latency": _p("lognormal", "nominal"),
    "user.patience_questions": _p("count", "nominal"),
    "user.p_no_answer": _p("prob", "user_noise"),
    "user.p_interrupt_stop": _p("prob", "user_noise"),
    "user.interrupt_after_calls": _p("range", "nominal"),
    "user.gait_mps_men": _p("map", "nominal", ['20-29', '30-39', '40-49', '50-59', '60-69', '70-79', '80-99']),
    "user.gait_mps_women": _p("map", "nominal", ['20-29', '30-39', '40-49', '50-59', '60-69', '70-79', '80-99']),
    "user.gait_older": _p("normal", "nominal"),
    "user.gait_child_mps": _p("speed_mps", "nominal"),
    "user.indoor_gait_factor": _p("value", "nominal"),
    "user.motion.rate_per_h": _p("rate_per_h", "user_noise"),
    "user.motion.pause_s": _p("range_s", "nominal"),
    "user.hearing_range_m": _p("distance_m", "nominal"),
    "user.p_location_unknown": _p("prob", "user_noise"),
    "user.handover_latency": _p("lognormal", "nominal"),
    "user.handover_timeout_s": _p("duration_s", "nominal"),
    "user.p_unresponsive": _p("prob", "user_noise"),
    "user.approach_distance_m": _p("distance_m", "nominal"),
    "user.asr_on_instruction": _p("flag", "nominal"),
    "user.dialog_channel": _p("value", "nominal", ["app", "voice"]),
    "safety.mode": _p("value", "nominal", ['monitored', 'static']),
    "safety.v_h_far": _p("speed_mps", "nominal"),
    "safety.v_h_near": _p("speed_mps", "nominal"),
    "safety.v_h_switch_m": _p("distance_m", "nominal"),
    "safety.v_h_margin": _p("speed_mps", "nominal"),
    "safety.T_r": _p("duration_s", "nominal"),
    "safety.a_max_arm": _p("accel_mps2", "nominal"),
    "safety.a_max_base": _p("accel_mps2", "nominal"),
    "safety.C": _p("distance_m", "nominal"),
    "safety.Z_d": _p("distance_m", "nominal"),
    "safety.Z_r": _p("distance_m", "nominal"),
    "safety.severe_m": _p("distance_m", "nominal"),
    "safety.arm_speed_mps": _p("speed_mps", "nominal"),
    "safety.handover_distance_m": _p("distance_m", "nominal"),
    "safety.handover_speed_mps": _p("speed_mps", "nominal"),
    "safety.muted_speed_mps": _p("speed_mps", "nominal"),
    "safety.stop_timeout_s": _p("duration_s", "nominal"),
    "safety.p_detection_miss": _p("prob", "safety_noise"),
    "safety.t_r_jitter_s": _p("duration_s", "nominal"),
    "safety.p_latency_jitter": _p("prob", "safety_noise"),
    "safety.personal_zone_m": _p("distance_m", "nominal"),
    # END user-safety
    "reach.grip_reach_m": _p("distance_m", "nominal"),
    "reach.body_offset_m": _p("distance_m", "nominal"),
    "reach.lean_seated_m": _p("distance_m", "nominal"),
    "reach.lean_standing_m": _p("distance_m", "nominal"),
    "reach.lean_standing_frail_m": _p("distance_m", "nominal"),
    "reach.band_seated_m": _p("range", "nominal"),
    "reach.band_standing_m": _p("range", "nominal"),
}


class ProfileError(ValueError):
    pass


_MISSING = object()


class Profile:
    """A resolved profile: ``get(name)`` -> value, ``entry(name)`` -> the full entry dict."""

    def __init__(self, name: str, params: dict, meta: dict | None = None):
        self.name = name
        self.params = params                 # name -> entry (with "value")
        self.meta = meta or {}
        blob = json.dumps({k: params[k].get("value") for k in sorted(params)}, sort_keys=True,
                          ensure_ascii=False, separators=(",", ":"), default=str)
        self.sha = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get(self, name: str, default=_MISSING):
        e = self.params.get(name)
        if e is None:
            if default is _MISSING:
                raise KeyError(f"profile {self.name}: no parameter {name!r}")
            return default
        return e.get("value")

    def has(self, name: str) -> bool:
        return name in self.params

    def entry(self, name: str) -> dict:
        return self.params[name]

    def values(self) -> dict:
        return {k: self.params[k].get("value") for k in sorted(self.params)}

    def __repr__(self) -> str:
        return f"Profile({self.name!r}, {len(self.params)} params, sha={self.sha[:10]})"


def _read_yaml(path: Path) -> dict:
    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(d, dict):
        raise ProfileError(f"{path}: top level must be a mapping")
    return d


def load_real_fragments() -> tuple:
    """(params, fragments, duplicate-key errors) of profiles/real/*.yaml."""
    params, frags, errs = {}, {}, []
    for f in sorted((PROFILE_DIR / "real").glob("*.yaml")):
        d = _read_yaml(f)
        frags[f.name] = d
        for k, v in (d.get("params") or {}).items():
            if k in params:
                errs.append(f"{f.name}: parameter {k!r} already defined in {params[k]['_file']}")
                continue
            e = dict(v or {})
            e["_file"] = f.name
            params[k] = e
    return params, frags, errs


def _is_prob_kind(e: dict) -> bool:
    return e.get("kind") in PROB_KINDS


def zero_value(e: dict):
    if e.get("kind") == "prob":
        return 0.0
    if e.get("kind") == "prob_map":
        return {k: 0.0 for k in (e.get("value") or {})}
    if e.get("kind") == "rate_per_h":
        return 0.0
    return e.get("value")


def scale_value(e: dict, factor: float, cap: float):
    v = e.get("value")
    if e.get("kind") == "prob":
        return min(cap, float(v) * factor)
    if e.get("kind") == "prob_map":
        return {k: min(cap, float(x) * factor) for k, x in v.items()}
    if e.get("kind") == "rate_per_h":
        return float(v) * factor
    return v


def derive(real_params: dict, spec: dict) -> tuple:
    """Apply an ``ideal`` / ``stress`` spec to the real params -> (params, notes)."""
    params = copy.deepcopy(real_params)
    notes = []
    for rule in spec.get("rules") or []:
        if "match" in rule:
            roles = set((rule.get("match") or {}).get("role") or [])
            for k in sorted(params):
                e = params[k]
                if e.get("role") in roles and rule.get("set") == "zero":
                    e["value"] = zero_value(e)
        elif "param" in rule:
            k = rule["param"]
            if k not in params:
                notes.append(f"rule for {k}: parameter not in real (skipped)")
                continue
            params[k]["value"] = copy.deepcopy(rule.get("set"))
    sc = spec.get("scaling")
    if sc:
        f, cap = float(sc.get("failure_prob_factor", 1.0)), float(sc.get("cap", 1.0))
        for k in sorted(params):
            e = params[k]
            if e.get("role") == "failure" and e.get("kind") in ("prob", "prob_map", "rate_per_h"):
                e["value"] = scale_value(e, f, cap)
    for k, ov in (spec.get("overrides") or {}).items():
        if k not in params:
            notes.append(f"override for {k}: parameter not in real (skipped)")
            continue
        params[k]["value"] = copy.deepcopy(ov.get("value"))
        params[k]["override"] = {x: ov[x] for x in sorted(ov) if x != "value"}
    return params, notes


def load_spec(name: str) -> dict:
    return _read_yaml(PROFILE_DIR / name / "profile.yaml")


@functools.lru_cache(maxsize=None)
def _load(name: str) -> Profile:
    if "+" in name:
        return _with_overrides(name)
    real, _frags, errs = load_real_fragments()
    if errs:
        raise ProfileError("; ".join(errs))
    if name == "real":
        return Profile("real", real)
    if name not in PROFILES:
        raise ProfileError(f"unknown profile {name!r} (have {', '.join(PROFILES)})")
    spec = load_spec(name)
    if spec.get("derive_from") != "real":
        raise ProfileError(f"{name}: derive_from must be real")
    params, notes = derive(real, spec)
    return Profile(name, params, {"notes": notes, "spec": spec})


def _with_overrides(name: str) -> Profile:
    """``"real+asr.ko.app_cer=0.02,asr.en.app_wer=0"``: a base profile with scalar parameters set (sensitivity runs,
    docs/profiles.md). Only existing scalar (number) parameters can be set; each is marked ``override: true``."""
    base, _, spec = name.partition("+")
    prof = _load(base)
    params = copy.deepcopy(prof.params)
    for item in [x for x in spec.split(",") if x.strip()]:
        key, eq, val = item.partition("=")
        key = key.strip()
        if not eq or key not in params:
            raise ProfileError(f"{name}: unknown parameter {key!r}")
        old = params[key].get("value")
        if isinstance(old, bool) or not isinstance(old, (int, float)):
            raise ProfileError(f"{name}: {key} is not a scalar number")
        try:
            v = float(val)
        except ValueError:
            raise ProfileError(f"{name}: {key}={val!r} is not a number") from None
        if params[key].get("kind") == "prob" and not 0.0 <= v <= 1.0:
            raise ProfileError(f"{name}: {key}={v} is not a probability")
        params[key]["value"] = v
        params[key]["override"] = True
    return Profile(name, params, dict(prof.meta, base=base))


def load_profile(name: str) -> Profile:
    """The resolved profile (cached; treat it as read-only). ``name`` may carry overrides:
    ``real+asr.ko.app_cer=0.02`` (see :func:`_with_overrides`)."""
    return _load(str(name))


def list_profiles() -> list:
    return list(PROFILES)
