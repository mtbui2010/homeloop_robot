"""The user / ASR / safety parameter fragments of the real profile: complete, typed, sourced, derivable."""
import re

import pytest
import yaml

from _hs_helpers import FRAGMENTS, NOISE_ROLES, ROOT, load_entries, load_params
from homeloop_robot import asr, safety, user

SOURCE_RE = re.compile(r"^(https?://\S+|doi:10\.\S+|arXiv:\d{4}\.\d{4,5})$")
KINDS = {"prob", "prob_map", "split", "range_s", "duration_s", "speed_mps", "accel_mps2", "distance_m", "mass_kg",
         "rate_per_h", "count", "lognormal", "normal", "categorical", "flag", "factor"}
ROLES = {"failure", "recovery", "nominal", "user_noise", "safety_noise"}
CAL = ROOT / "docs" / "calibration.md"


def block(text: str) -> str:
    a = text.index("<!-- BEGIN user-safety sources -->")
    b = text.index("<!-- END user-safety sources -->")
    return text[a:b]


def test_registry_matches_yaml():
    keys = set(load_entries())
    reg = set(user.PARAMS) | set(asr.PARAMS) | set(safety.PARAMS)
    assert keys == reg, (keys - reg, reg - keys)
    assert len(reg) == len(user.PARAMS) + len(asr.PARAMS) + len(safety.PARAMS)


def test_fragment_headers():
    parts = set()
    for f in FRAGMENTS:
        doc = yaml.safe_load(f.read_text())
        assert doc["profile"] == "real"
        parts.add(doc["part"])
    assert parts == {"user", "safety"}


@pytest.mark.parametrize("name", sorted(load_entries()))
def test_entry_is_well_formed(name):
    e = load_entries()[name]
    assert e["kind"] in KINDS and e["role"] in ROLES
    assert "value" in e and len(e.get("note", "")) >= 20
    v = e["value"]
    if e["kind"] == "prob":
        assert 0.0 <= v <= 1.0
    if e["kind"] in ("duration_s", "speed_mps", "accel_mps2", "factor") and not isinstance(v, dict):
        assert v > 0 or (e["role"] == "safety_noise" and v >= 0)
    if e["kind"] == "range_s":
        assert v[0] <= v[1]
    if e["kind"] == "lognormal":
        assert v["median"] > 0 and v["sigma"] > 0 and v["min"] >= 0
    if e["kind"] == "normal":
        assert v["sd"] > 0 and v["min"] < v["mean"] < v["max"]
    if "keys" in e and isinstance(v, dict):
        assert sorted(map(str, e["keys"])) == sorted(map(str, v))
    if e["kind"] == "categorical" and isinstance(v, dict):
        assert sum(v.values()) == pytest.approx(1.0)
    if e.get("assumed"):
        if "anchor" in e:
            assert SOURCE_RE.match(e["anchor"])
    else:
        assert SOURCE_RE.match(e["source"]) and e["where"].strip()


def test_every_source_listed_in_calibration_block():
    text = block(CAL.read_text())
    for name, e in load_entries().items():
        for key in ("source", "anchor"):
            if key in e:
                assert e[key] in text, f"{name}: {e[key]} missing from docs/calibration.md user-safety block"


def test_assumed_params_listed_in_docs():
    text = block(CAL.read_text())
    for name, e in load_entries().items():
        if e.get("assumed"):
            assert f"`{name}`" in text, f"assumed {name} not listed in the Assumptions table"


def test_ideal_derivation_zeroes_noise():
    real, ideal = load_params("real"), load_params("ideal")
    entries = load_entries()
    for k, e in entries.items():
        if e["role"] in NOISE_ROLES:
            v = ideal[k]
            flat = list(v.values()) if isinstance(v, dict) else (v if isinstance(v, list) else [v])
            assert all(x == 0 or x is False for x in flat), k
        elif k != "user.motion.rate_per_h":
            assert ideal[k] == real[k], k
    assert ideal["user.motion.rate_per_h"] == 0


def test_stress_block_when_present():
    f = ROOT / "homeloop_robot" / "profiles" / "stress" / "profile.yaml"
    if not f.exists():
        pytest.skip("stress profile (robot core) not present")
    text = f.read_text()
    assert "# BEGIN user-safety overrides" in text and "# END user-safety overrides" in text
    doc = yaml.safe_load(text)
    entries = load_entries()
    for k, ov in (doc.get("overrides") or {}).items():
        if k.split(".")[0] in ("user", "asr", "safety"):
            assert k in entries, k
            assert "note" in ov and ("source" in ov or ov.get("assumed"))
