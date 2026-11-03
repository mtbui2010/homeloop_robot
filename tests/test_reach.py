"""Round 2 delivery: support surfaces, posture, the reach predicate, delivered(), the mode choice, and the
oracle that never reads the task's mode label (docs/reach.md)."""

import dataclasses
import math

import pytest

from helpers import HAS_RA, episode
from homeloop_robot import goals as G
from homeloop_robot import oracle, reach
from homeloop_robot.houses import list_houses, load_house, validate_house
from homeloop_robot.world import from_house


def dl(obj, person, mode, reason=None):
    return {"pred": "delivered", "args": [obj, person], "mode": mode, "mode_reason": reason}


def put(w, oid, pid):
    o = w.objects[oid]
    o.at, o.inside = pid, w.place(pid).kind == "container"


# ── world model ─────────────────────────────────────────────────────────────────────────────────────────

def test_surface_types_and_support():
    h = load_house("senior_flat")
    t = {pid: reach.surface_type(p) for pid, p in h.places.items()}
    assert t["side_table@living"] == "table" and t["nightstand@bedroom"] == "nightstand"
    assert t["counter@kitchen"] == "counter" and t["shelf@kitchen"] == "shelf"
    assert t["armchair@living"] == "seat" and t["bed@bedroom"] == "bed" and t["floor@living"] == "floor"
    assert t["stove@kitchen"] == "stove" and t["kitchen_sink@kitchen"] == "sink"
    sup = {pid for pid, p in h.places.items() if reach.is_support(p)}
    assert "armchair@living" not in sup and "bed@bedroom" not in sup and "floor@living" not in sup
    assert "fridge@kitchen" not in sup and "stove@kitchen" not in sup and "tv_stand@living" not in sup
    assert {"side_table@living", "nightstand@bedroom", "counter@kitchen", "coffee_table@living"} <= sup


def test_houses_valid_and_some_places_have_no_reachable_surface():
    none, some = [], []
    for h in list_houses():
        assert validate_house(load_house(h)) == []
        w = from_house(h, 0)
        for pid, p in w.people.items():
            for s in [p.seat] + p.alt_seats + p.walks_to:
                pos = p.pos if s == p.seat else w.place(s).person_pos
                (some if reach.reachable_surfaces(w, pid, reach.person_pose(w, pid, pos=pos)) else none).append(
                    (h, pid, s))
    assert ("family_house", "mom", "bed@master") in none           # a bed without a nightstand
    assert ("family_house", "mom", "front_door@entrance") in none  # standing in the entrance hall
    assert ("couple_flat", "partner_b", "reading_chair@bedroom") in none   # a seat with no table nearby
    assert ("senior_flat", "grandma", "armchair@living") in some and len(some) >= 10 and len(none) >= 6


def test_posture_seated_standing_walking():
    w = from_house("family_house", 0)
    p = reach.person_pose(w, "mom")
    assert (p.posture, p.place, p.moving) == ("seated", "sofa@living", False)
    w.people_now = {"mom": {"pos": tuple(w.place("bed@master").person_pos), "moving": False}}
    assert reach.person_pose(w, "mom").posture == "seated" and reach.person_pose(w, "mom").place == "bed@master"
    w.people_now = {"mom": {"pos": tuple(w.place("front_door@entrance").person_pos), "moving": False}}
    p = reach.person_pose(w, "mom")
    assert (p.posture, p.place, p.room) == ("standing", "front_door@entrance", "entrance")
    w.people_now = {"mom": {"pos": (0.5, 0.5), "moving": True}}            # walking past the sofa
    assert reach.person_pose(w, "mom").posture == "standing"
    # a person whose usual place is a desk sits at it
    assert reach.person_pose(from_house("shared_flat", 0), "roommate_c").posture == "seated"


def test_radius_and_band_from_profile():
    prm = reach.default_params()
    assert prm.radius("seated") == pytest.approx(0.58 - 0.12 + 0.168)
    assert prm.radius("standing") == pytest.approx(0.58 - 0.12 + 0.194)
    assert prm.radius("standing", frail=True) == pytest.approx(0.58 - 0.12 + 0.154)
    assert prm.band("seated") == (0.38, 1.12) and prm.band("standing") == (0.38, 1.22)


# ── reach and delivered: success cases ──────────────────────────────────────────────────────────────────

def test_reach_on_side_table_succeeds_hand_does_not():
    w = from_house("senior_flat", 0)
    put(w, "mug_1", "side_table@living")
    assert reach.reachable("mug_1", "grandma", w)
    assert G.evaluate({"all": [dl("mug_1", "grandma", "reach")]}, w).holds
    assert not G.evaluate({"all": [dl("mug_1", "grandma", "hand", "explicit")]}, w).holds


def test_handover_satisfies_both_modes():
    w = from_house("senior_flat", 0)
    w.objects["mug_1"].at = "person:grandma"
    for m, r in (("reach", None), ("hand", "explicit"), ("hand", "no_surface"), ("hand", "user_needs")):
        assert G.holds(dl("mug_1", "grandma", m, r), w)
    assert not G.holds(dl("mug_2", "grandma", "reach"), w)


def test_reach_at_desk_and_coffee_table():
    w = from_house("korean_apt_84", 0)
    put(w, "mug_1" if "mug_1" in w.objects else sorted(w.objects)[0], "coffee_table@living")
    oid = "mug_1" if "mug_1" in w.objects else sorted(w.objects)[0]
    assert G.holds(dl(oid, "mom", "reach"), w)
    w = from_house("studio_flat", 0)
    oid = sorted(o for o in w.objects if w.objects[o].at != "desk@main")[0]
    put(w, oid, "desk@main")
    assert G.holds(dl(oid, "user", "reach"), w)


# ── reach and delivered: failure cases ──────────────────────────────────────────────────────────────────

def test_seat_floor_bed_and_far_surface_fail():
    w = from_house("senior_flat", 0)
    for pid in ("armchair@living", "floor@living", "coffee_table@living", "tv_stand@living", "counter@kitchen"):
        put(w, "mug_1", pid)
        assert not G.holds(dl("mug_1", "grandma", "reach"), w), pid
    w.people_now = {"grandma": {"pos": tuple(w.place("bed@bedroom").person_pos), "moving": False}}
    put(w, "mug_1", "bed@bedroom")
    assert not G.holds(dl("mug_1", "grandma", "reach"), w)
    put(w, "mug_1", "nightstand@bedroom")
    assert G.holds(dl("mug_1", "grandma", "reach"), w)


def test_inside_a_container_fails():
    w = from_house("senior_flat", 0)
    put(w, "mug_1", "drawer@kitchen")
    assert not reach.reachable("mug_1", "grandma", w)


def test_height_band_and_radius_fail():
    w = from_house("senior_flat", 0)
    put(w, "mug_1", "side_table@living")
    low = dataclasses.replace(reach.default_params(), band_seated_m=(0.6, 1.12))
    assert not reach.reachable("mug_1", "grandma", w, params=low)        # 0.55 m table below the band
    short = dataclasses.replace(reach.default_params(), grip_reach_m=0.3)
    assert not reach.reachable("mug_1", "grandma", w, params=short)


def test_person_moved_away_is_judged_where_they_are():
    w = from_house("senior_flat", 0)
    put(w, "mug_1", "side_table@living")
    assert G.holds(dl("mug_1", "grandma", "reach"), w)
    w.people_now = {"grandma": {"pos": tuple(w.place("bed@bedroom").person_pos), "moving": False}}
    assert not G.holds(dl("mug_1", "grandma", "reach"), w)


def test_robot_syncs_people_now():
    ep = episode("senior_flat")
    assert ep.world.people_now["grandma"]["pos"] == tuple(ep.world.people["grandma"].pos)
    ep.robot.call("wait", seconds=1)
    assert set(ep.world.people_now) == {"grandma"}


def test_goal_text_form_and_validation():
    g = G.parse("delivered[reach](mug_1, grandma) & delivered[hand](phone_1, grandma)")
    assert g["all"][0] == {"pred": "delivered", "args": ["mug_1", "grandma"], "mode": "reach"}
    assert G.format(g) == "delivered[reach](mug_1, grandma) & delivered[hand](phone_1, grandma)"
    w = from_house("senior_flat", 0)
    assert G.validate(g, w) == []
    assert G.validate({"all": [dl("mug_1", "grandma", "sideways")]}, w)
    assert G.validate({"all": [dl("mug_1", "grandma", "reach", "explicit")]}, w)
    assert G.validate({"all": [dl("mug_1", "grandma", "hand", "because")]}, w)
    assert G.validate({"all": [dl("mug_1", "nobody", "hand", "explicit")]}, w)


# ── observation and mode choice ─────────────────────────────────────────────────────────────────────────

def test_person_view_has_no_label():
    w = from_house("senior_flat", 0)
    v = reach.person_view(w, "grandma")
    assert v["posture"] == "seated" and v["place"] == "armchair@living" and v["prefers_handover"] is False
    assert "side_table@living" in [n["place"] for n in v["nearby"]]
    flat = repr(v)
    assert "mode" not in flat and "reachable" not in flat and "hand" not in flat.replace("prefers_handover", "")


@pytest.mark.parametrize("text,lang,want", [
    ("Could you hand me my glasses?", "en", True), ("Please put the remote in my hand.", "en", True),
    ("Bring me the hand cream.", "en", False), ("Bring me the hand towel, please.", "en", False),
    ("I washed it by hand; bring me the mug.", "en", False), ("Bring me my glasses.", "en", False),
    # the noun "hands" after a possessive is not a request (review round 1: 17 tasks were mislabelled explicit)
    ("My hands are full with the cooking. Could you bring me the cup?", "en", False),
    ("I just washed my hands. Please bring me a towel.", "en", False),
    ("I just wiped my hands, grab that white mug for me.", "en", False),
    ("My hand hurts; bring me the mug.", "en", False),
    ("Can you hand the bleach to my husband?", "en", True), ("Hand grandpa the cell phone.", "en", True),
    ("Please put it right in his hand.", "en", True), ("I'd like it handed to me.", "en", True),
    ("Please hand it over.", "en", True),
    ("지금 요리하느라 손이 없어요. 컵 좀 가져다주세요.", "ko", False), ("손을 씻었어요. 수건 좀 갖다주세요.", "ko", False),
    ("안경 좀 건네주세요.", "ko", True), ("리모컨을 제 손에 쥐여 주세요.", "ko", True),
    ("안경 좀 가져다주세요.", "ko", False), ("손님 컵 좀 가져다주세요.", "ko", False)])
def test_wording_wants_hand(text, lang, want):
    assert reach.wording_wants_hand(text, lang) is want


def test_full_surface_is_not_a_hand_requirement():
    """need() is geometry only: a reachable surface that is full is still reach; the robot's own choice
    (choose_mode) is then a handover (surface_full), which satisfies reach."""
    w = from_house("senior_flat", 0)
    s = reach.reachable_surfaces(w, "grandma")
    assert s
    cap = {p: w.free_slots(p) for p in s}
    filler = sorted(o for o in w.objects if w.objects[o].at not in s)
    for p in s:
        for _ in range(cap[p]):
            w.objects[filler.pop()].at = p
    assert all(w.free_slots(p) <= 0 for p in s)
    assert reach.need(w, "grandma") == ("reach", None)
    assert reach.choose_mode(w, "grandma") == reach.ModeChoice("hand", "surface_full", None)


def test_choose_mode_reasons():
    w = from_house("senior_flat", 0)
    assert reach.choose_mode(w, "grandma", "Bring me my glasses.") == reach.ModeChoice("reach", None,
                                                                                         "side_table@living")
    assert reach.choose_mode(w, "grandma", "Hand me my glasses.").reason == "explicit"
    assert reach.choose_mode(from_house("care_home_suite", 0), "resident", "").reason == "user_needs"
    fam = from_house("family_house", 0)
    fam.people_now = {"mom": {"pos": tuple(fam.place("bed@master").person_pos), "moving": False}}
    assert reach.choose_mode(fam, "mom", "") == reach.ModeChoice("hand", "no_surface", None)
    assert reach.need(fam, "mom", "") == ("hand", "no_surface")
    assert reach.need(from_house("korean_apt_59", 0), "grandpa", "") == ("hand", "user_needs")


# ── oracle: chooses from words and scene, never from the label ───────────────────────────────────────────

def _strip(goal):
    return {"all": [{k: v for k, v in a.items() if k not in ("mode", "mode_reason")} for a in goal["all"]]}


@pytest.mark.parametrize("house,person,text", [
    ("senior_flat", "grandma", "Bring me the red mug."), ("senior_flat", "grandma", "Hand me the red mug."),
    ("care_home_suite", "resident", "Bring me the mug."), ("family_house", "mom", "Bring me a mug.")])
def test_oracle_never_reads_mode(house, person, text):
    w = from_house(house, 0)
    oid = sorted(o for o in w.objects if oracle.solve(w, {"all": [dl(o, person, "hand", "explicit")]}))[0]
    plans = []
    for m, r in (("reach", None), ("hand", "explicit"), ("hand", "no_surface"), (None, None)):
        g = {"all": [dl(oid, person, m, r)]} if m else _strip({"all": [dl(oid, person, "reach")]})
        g["all"][0]["pred"] = "delivered"
        plans.append(oracle.solve(w, g, text=text))
    assert plans[0] is not None and all(p == plans[0] for p in plans)
    assert oracle.delivery_modes(w, {"all": [dl(oid, person, "hand", "explicit")]}, text=text) == \
        oracle.delivery_modes(w, {"all": [dl(oid, person, "reach")]}, text=text)


def test_oracle_reach_places_hand_hands_over_ideal():
    ep = episode("senior_flat")
    g = {"all": [dl("mug_1", "grandma", "reach")]}
    plan = oracle.solve(ep.world, g, text="Bring me the red mug.")
    assert [c.skill for c in plan][-1] == "place" and plan[-1].args == {"target": "side_table@living"}
    for c in plan:
        assert ep.robot.call(c.skill, **c.args).ok
    assert G.evaluate(g, ep.world).holds
    ep = episode("senior_flat")
    g = {"all": [dl("mug_1", "grandma", "hand", "explicit")]}
    plan = oracle.solve(ep.world, g, text="Hand me the red mug.")
    assert plan[-1].skill == "handover"
    for c in plan:
        assert ep.robot.call(c.skill, **c.args).ok
    assert G.evaluate(g, ep.world).holds


@pytest.mark.parametrize("house", list_houses())
def test_oracle_rollout_ideal_every_house_and_person(house):
    for pid in sorted(from_house(house, 0).people):
        ep = episode(house)
        w = ep.world
        oid = sorted(o for o in w.objects if oracle.solve(w, {"all": [dl(o, pid, "hand", "explicit")]}))[0]
        mode = reach.choose_mode(w, pid, "Bring it to me.")
        g = {"all": [dl(oid, pid, mode.mode, mode.reason)]}
        assert oracle.rollout(ep, g, text="Bring it to me.")["success"], (house, pid, mode)


def test_claimed_done_on_a_seat_is_not_success():
    ep = episode("senior_flat")
    for c in oracle.solve(ep.world, {"all": [{"pred": "on", "args": ["mug_1", "armchair@living"]}]}):
        assert ep.robot.call(c.skill, **c.args).ok
    assert not G.evaluate({"all": [dl("mug_1", "grandma", "reach")]}, ep.world).holds


# ── robot_agent adapter: "near the person" resolves to a real reachable surface ──────────────────────────

@pytest.mark.skipif(not HAS_RA, reason="robot_agent not importable")
def test_adapter_person_place_resolves_to_reachable_surface():
    from homeloop_robot.configs.adapter import make_adapter
    from homeloop_robot.configs.backend import reset_backend, set_backend
    from homeloop_robot.configs.tasks import env_for
    ep = episode("senior_flat")
    set_backend(ep.robot)
    try:
        ad = make_adapter()
        assert ad.bind({"action": "MoveTo", "object": "grandma"}) == ("move", {"inputs": "side_table@living"})
        assert ad.bind({"action": "Place", "object": "grandma"}) == ("place", {"inputs": "side_table@living"})
        env = env_for(ep.world)
        assert env["grandma"]["loc"]["x"] == ep.world.place("side_table@living").pos[0]
    finally:
        reset_backend()
    ep = episode("family_house")
    ep.world.people_now = {"mom": {"pos": tuple(ep.world.place("bed@master").person_pos), "moving": False}}
    set_backend(ep.robot)
    try:
        ad = make_adapter()
        # no free surface beside her: Place stays a Place aimed at her (it fails); never a silent handover
        assert ad.bind({"action": "Place", "object": "mom"}) == ("place", {"inputs": "mom"})
        assert ad.bind({"action": "MoveTo", "object": "mom"}) == ("move", {"inputs": "mom"})
    finally:
        reset_backend()


@pytest.mark.parametrize("house", list_houses())
def test_user_answers_to_me_in_every_house(house):
    """The speaker resolves as 'me' / 나 / 저 in every house (a name translation for the adapter)."""
    w = from_house(house, 0)
    uid = w.user_id()
    for name in ("me", "나", "저"):
        assert w.resolve_person(name, None) == uid, (house, name)


def test_person_spot_is_geometry_only():
    """adapter.person_spot does not use the judge: nearest free support surface within Hall's 1.2 m, whatever its
    height or the person's posture."""
    from homeloop_robot.configs.tasks import PERSON_SPOT_RADIUS_M, person_spot
    assert PERSON_SPOT_RADIUS_M == 1.2
    for house in list_houses():
        w = from_house(house, 0)
        for pid in sorted(w.people):
            spot = person_spot(w, pid)
            if spot is None:
                continue
            pl = w.house.places[spot]
            assert reach.is_support(pl) and w.free_slots(spot) > 0
            assert math.dist(reach.surface_xy(pl), w.person_xy(pid)) <= 1.2 + 1e-9


def test_person_spot_may_be_out_of_reach_and_then_the_delivery_fails():
    """A support surface within Hall's 1.2 m whose height is outside the seated band (a wall shelf at 1.6 m beside
    the armchair): person_spot still picks it (geometry only, no judge), the object put there is not delivered in
    reach mode, and a handover still is."""
    from homeloop_robot.configs.tasks import person_spot
    w = from_house("senior_flat", 0)
    spot = person_spot(w, "grandma")
    assert spot == "side_table@living" and reach.place_reachable(w, spot, "grandma")
    pl = w.house.places[spot]
    h0 = pl.height_m
    try:
        object.__setattr__(pl, "height_m", 1.6)
        assert person_spot(w, "grandma") == spot                      # still chosen: within 1.2 m, free
        assert not reach.place_reachable(w, spot, "grandma")          # above the seated band
        put(w, "mug_1", spot)
        assert not G.holds(dl("mug_1", "grandma", "reach"), w)
        w.objects["mug_1"].at, w.objects["mug_1"].inside = "person:grandma", False
        assert G.holds(dl("mug_1", "grandma", "reach"), w)
    finally:
        object.__setattr__(pl, "height_m", h0)
