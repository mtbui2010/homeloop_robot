"""Consistency fix: a robot that waits without a skill call (Robot.idle) lets simulated time pass, and a long enough
idle run clears a camera fault that clears on waiting, as the wait skill does."""
import pytest

from homeloop_robot.episode import make_episode
from homeloop_robot.types import FailureCode, FaultState


def _down(ep):
    ep.world.faults["camera"] = FaultState(device="camera", code=FailureCode.PERCEPTION_UNAVAILABLE, since_t=0.0,
                                           clears_on="wait", p_clear=1.0)


def test_idle_advances_the_clock_and_is_deterministic():
    a, b = make_episode("senior_flat", 0, "real", 0), make_episode("senior_flat", 0, "real", 0)
    for ep in (a, b):
        _down(ep)
        ep.robot.idle(2.5)
        ep.robot.idle(2.5)
    assert a.clock.t == pytest.approx(5.0) == b.clock.t
    assert ("camera" in a.world.faults) == ("camera" in b.world.faults) is False


def test_short_idle_does_not_clear_and_zero_is_a_noop():
    ep = make_episode("senior_flat", 0, "real", 0)
    _down(ep)
    assert ep.robot.idle(0.0) == 0.0 and ep.robot.idle(4.9) == pytest.approx(4.9)
    assert "camera" in ep.world.faults
