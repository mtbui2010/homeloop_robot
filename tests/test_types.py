import importlib.util

import pytest

from homeloop_robot.types import FailureCode, SkillResult


def test_result_shapes():
    r = SkillResult(ok=False, code=FailureCode.ABSENT, msg="mug_1 not found", data={"x": 1.23456789},
                    duration_s=2.0000001, injected=True, truth={"event": "miss"})
    assert r.public() == {"ok": False, "code": "absent", "msg": "mug_1 not found", "data": {"x": 1.234568},
                          "duration_s": 2.0}
    leg = r.to_legacy()
    assert leg["isdone"] is False and leg["code"] == "absent" and leg["msg"] == "mug_1 not found"
    assert r.to_json()["injected"] is True and r.to_json()["truth"] == {"event": "miss"}


@pytest.mark.skipif(importlib.util.find_spec("robot_agent") is None, reason="robot_agent not importable")
def test_codes_match_robot_agent():
    from robot_agent.contract import FailureCode as RA
    ra = {c.value for c in RA}
    for c in FailureCode:
        assert c.value in ra
