import io

import pytest

from homeloop_robot.profiles import PARAM_REGISTRY, list_profiles, load_profile
from homeloop_robot.profiles.validate import norm_source, run


def test_three_profiles_same_keys():
    assert list_profiles() == ["ideal", "real", "stress"]
    keys = set(load_profile("real").params)
    assert keys == set(PARAM_REGISTRY)
    assert set(load_profile("ideal").params) == keys == set(load_profile("stress").params)


def test_ideal_zero_failures_and_stress_scaled():
    real, ideal, stress = (load_profile(n) for n in ("real", "ideal", "stress"))
    for k, e in real.params.items():
        if e["role"] == "failure" and e["kind"] == "prob":
            assert ideal.get(k) == 0
            if k not in stress.meta["spec"].get("overrides", {}):
                assert stress.get(k) == min(0.95, 2 * e["value"])
        if e["role"] == "recovery":
            assert ideal.get(k) == e["value"] == stress.get(k)
    assert stress.get("open.p_fail") == {"door": 0.5, "drawer": 0.5}
    assert ideal.get("pose.sigma_m") == 0
    assert real.sha != ideal.sha != stress.sha


def test_validator_strict_passes():
    out = io.StringIO()
    code = run(strict=True, out=lambda s: out.write(s + "\n"))
    assert code == 0, out.getvalue()
    assert "assumed:" in out.getvalue()


def test_norm_source():
    assert norm_source("https://arxiv.org/pdf/2401.12202v2") == "arxiv:2401.12202"
    assert norm_source("arXiv:2401.12202") == "arxiv:2401.12202"
    assert norm_source("https://doi.org/10.1016/J.X.1") == "doi:10.1016/j.x.1"


def test_profile_overrides_for_sensitivity_runs():
    from homeloop_robot.profiles import ProfileError, load_profile
    p = load_profile("real+asr.ko.app_cer=0.01,asr.en.app_wer=0")
    assert p.get("asr.ko.app_cer") == 0.01 and p.get("asr.en.app_wer") == 0.0
    assert p.sha != load_profile("real").sha and load_profile("real").get("asr.ko.app_cer") == 0.0521
    assert p.get("hw.p_per_motion_call") == load_profile("real").get("hw.p_per_motion_call")
    for bad in ("real+nope=1", "real+asr.ko.app_cer=2", "real+asr.ko.app_cer=x"):
        with pytest.raises(ProfileError):
            load_profile(bad)
