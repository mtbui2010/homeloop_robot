import json

from helpers import episode
from homeloop_robot import oracle
from homeloop_robot.episode import make_episode
from homeloop_robot.rng import rng_for
from homeloop_robot.selftest import random_call, random_goal


def trace(profile, seed, key, user_impl="null"):
    ep = make_episode("family_house", 5, profile, seed, key=key, user_impl=user_impl, safety_impl=user_impl)
    rng = rng_for("det")
    for _ in range(60):
        s, a = random_call(ep.world, rng)
        ep.robot.call(s, **a)
    return json.dumps(ep.robot.trace, sort_keys=True)


def test_same_seed_same_trace():
    assert trace("real", 1, "k") == trace("real", 1, "k")
    assert trace("real", 1, "k", None) == trace("real", 1, "k", None)       # with the full models, if installed
    assert trace("real", 1, "k") != trace("real", 2, "k")


def test_common_random_numbers():
    """The same call in two episodes with the same key draws the same outcome even when other calls
    differ in between (draws are keyed by skill, args and the call's repeat count)."""
    a, b = episode(profile="real", seed=9, key="crn"), episode(profile="real", seed=9, key="crn")
    b.robot.call("say", text="hello")
    b.robot.call("look")
    ra = a.robot.call("move", target="counter@kitchen")
    rb = b.robot.call("move", target="counter@kitchen")
    assert (ra.ok, ra.code, ra.truth) == (rb.ok, rb.code, rb.truth)


def test_oracle_deterministic():
    ep = episode("korean_apt_59", seed_state=3)
    g = random_goal(ep.world, rng_for("g"))
    assert [str(c) for c in oracle.solve(ep.world, g)] == [str(c) for c in oracle.solve(ep.world, g)]
