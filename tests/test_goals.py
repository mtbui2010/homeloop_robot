from homeloop_robot import goals
from homeloop_robot.types import Utterance
from homeloop_robot.world import from_house


def test_parse_format_roundtrip():
    s = "on(mug_1, counter@kitchen) & not open(drawer@kitchen) & any(on(mug_2, counter@kitchen) | in(mug_2, fridge@kitchen))"
    g = goals.parse(s)
    assert goals.format(g) == s
    assert goals.parse(goals.format(g)) == g
    r = goals.parse("refuse: unmoved(bleach_1)")
    assert r["refuse"] is True and goals.format(r) == "refuse: unmoved(bleach_1)"
    assert goals.parse("hand_empty() & docked()")["all"] == [{"pred": "hand_empty", "args": []},
                                                            {"pred": "docked", "args": []}]


def test_validate():
    w = from_house("senior_flat", 0)
    assert goals.validate(goals.parse("on(mug_1, coffee_table@living)"), w) == []
    assert goals.validate(goals.parse("on(mug_1, fridge@kitchen)"), w)            # container: use in
    assert goals.validate(goals.parse("in(mug_1, counter@kitchen)"), w)
    assert goals.validate(goals.parse("on(unicorn_1, counter@kitchen)"), w)
    assert goals.validate(goals.parse("said_to(grandma, no_such_msg)"), w)
    assert goals.validate(goals.parse("fly(mug_1)"), w)


def test_evaluate():
    w = from_house("senior_flat", 0)
    g = goals.parse("on(mug_1, counter@kitchen) & in(milk_1, fridge@kitchen) & open(fridge@kitchen)")
    ev = goals.evaluate(g, w)
    assert not ev.holds and abs(ev.fraction - 2 / 3) < 1e-9
    w.opened.add("fridge@kitchen")
    assert goals.evaluate(g, w).holds
    assert goals.evaluate(goals.parse("unmoved(bleach_1) & hand_empty() & docked()"), w).holds
    w.utterances.append(Utterance(t=1.0, skill="say", text="Dinner is ready.", lang="en", heard_by=("grandma",)))
    assert goals.evaluate(goals.parse("said_to(grandma, dinner_ready)"), w).holds
    assert not goals.evaluate(goals.parse("said_to(grandma, lunch_ready)"), w).holds
