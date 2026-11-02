import pytest

from helpers import episode
from homeloop_robot import goals, oracle
from homeloop_robot.houses import list_houses
from homeloop_robot.rng import rng_for
from homeloop_robot.selftest import random_goal


@pytest.mark.parametrize("house", list_houses())
def test_oracle_reaches_random_goals_in_ideal(house):
    n = 0
    for i in range(50):
        ep = episode(house, seed=i, seed_state=i)
        g = random_goal(ep.world, rng_for("oracle", house, i))
        if g is None:
            continue
        plan = oracle.solve(ep.world, g)
        assert plan is not None
        for c in plan:
            r = ep.robot.call(c.skill, **c.args)
            assert r.ok, (goals.format(g), str(c), r.msg)
        assert goals.evaluate(g, ep.world).holds, goals.format(g)
        n += 1
    assert n >= 40


def test_unsolvable_goals():
    w = episode().world
    assert oracle.solve(w, goals.parse("on(houseplant_1, counter@kitchen)")) is None   # heavy
    assert "heavy" in oracle.explain_unsolvable(w, goals.parse("on(houseplant_1, counter@kitchen)"))
    assert oracle.solve(w, goals.parse("on(tv_1, coffee_table@living)")) is None         # fixed
    assert oracle.solve(w, goals.parse("on(unicorn, counter@kitchen)")) is None          # invalid
    assert oracle.solve(w, goals.parse("unmoved(bleach_1)")) == []                       # already true
    assert oracle.explain_unsolvable(w, goals.parse("on(mug_1, coffee_table@living)")) == ""


def test_any_picks_the_cheaper_alternative():
    w = episode().world
    g = goals.parse("any(on(mug_1, nightstand@bedroom) | on(mug_1, stove@kitchen))")
    plan = oracle.solve(w, g)
    assert plan[-1].args == {"target": "stove@kitchen"}


def test_partial_open_is_reopened():
    ep = episode()
    ep.world.opened.add("fridge@kitchen")
    ep.world.robot.partial_open.add("fridge@kitchen")
    plan = oracle.solve(ep.world, goals.parse("in(mug_1, fridge@kitchen)"))
    skills = [c.skill for c in plan]
    assert skills[:3] == ["move", "close", "open"]


@pytest.mark.parametrize("profile,lo,hi", [("ideal", 1.0, 1.0), ("real", 0.5, 0.95)])
def test_closed_loop_oracle_composition(profile, lo, hi):
    """docs/failure_model.md: single-object rearrangement by the closed-loop oracle in `real` should land
    in the band spanned by OK-Robot (58.5-82 %) and SayCan execution (60-74 %); loose bounds."""
    ok = n = 0
    for house in list_houses():
        for i in range(12):
            ep = episode(house, profile, seed=i, seed_state=i, key=f"c{i}")
            rng = rng_for("comp", house, i)
            g = None
            for _ in range(30):
                cand = random_goal(ep.world, rng, max_atoms=1)
                if cand and cand["all"][0]["pred"] == "on":
                    g = cand
                    break
            if g is None:
                continue
            ok += oracle.rollout(ep, g)["success"]
            n += 1
    assert n >= 60 and lo <= ok / n <= hi, ok / n
