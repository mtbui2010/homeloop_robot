"""Oracle planning with full places (found by the bench's round 2 validation, tasks hl-train-003322 and
hl-dev-000967): a reach delivery leaves room for the goal's own on / in atoms, and an object is taken off a full
place before another one is put there."""

from homeloop_robot import oracle, reach
from homeloop_robot.world import from_house


def test_reach_delivery_leaves_room_for_an_on_atom():
    w = from_house("senior_flat", 904)                 # grandma in bed, one free slot on the nightstand
    assert w.people["grandma"].seat == "bed@bedroom" and w.free_slots("nightstand@bedroom") == 1
    assert reach.reachable_surfaces(w, "grandma", free_only=True) == ["nightstand@bedroom"]
    goal = {"all": [{"pred": "on", "args": ["mug_1", "nightstand@bedroom"]},
                    {"pred": "delivered", "args": ["keys_1", "grandma"], "mode": "reach", "mode_reason": None}]}
    plan = oracle.solve(w, goal, lang="en", modes={("keys_1", "grandma"): "reach"})
    assert plan is not None, oracle.explain_unsolvable(w, goal)
    # the free slot is the mug's; the keys are handed over (a handover satisfies reach)
    assert ("place", "nightstand@bedroom") in [(c.skill, c.args.get("target")) for c in plan]
    assert any(c.skill == "handover" for c in plan)


def test_object_taken_off_a_full_place_first():
    w = from_house("senior_flat", 1813)                # the nightstand is full, the phone is on it
    assert w.free_slots("nightstand@bedroom") == 0 and w.objects["phone_1"].at == "nightstand@bedroom"
    goal = {"all": [{"pred": "on", "args": ["book_2", "nightstand@bedroom"]},
                    {"pred": "on", "args": ["phone_1", "coffee_table@living"]}]}
    plan = oracle.solve(w, goal, lang="en")
    assert plan is not None, oracle.explain_unsolvable(w, goal)
    picks = [c.args.get("obj") for c in plan if c.skill == "pick"]
    assert picks.index("phone_1") < picks.index("book_2")
