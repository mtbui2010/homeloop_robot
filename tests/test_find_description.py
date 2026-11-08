"""Milestone 5 round 1 (KO hl-dev-000003): the planner looked for "white milk pack" (its English for 흰 우유팩) at the
table where the milk carton stood and got "no such object": the camera matched catalog names only. An
open-vocabulary detector reads a description: the object's name in the query, with extra words before it or a
packaging noun after it, and no colour word that contradicts the object's colour."""
from homeloop_robot.skills import detector_hits

from helpers import episode


def test_description_finds_and_picks_the_object():
    ep = episode("senior_flat")
    w = ep.world
    mugs = w.resolve_object("mug", None)
    assert mugs == ["mug_1", "mug_2"]
    col = w.objects["mug_1"].attrs.get("color")
    assert detector_hits(w, f"{col} coffee mug") == ["mug_1"]          # the other mug has another colour
    assert detector_hits(w, "mug rack") == []                          # another object named after it
    assert detector_hits(w, "spaceship") == []
    assert ep.robot.call("move", target="counter@kitchen").ok          # the red mug is here
    r = ep.robot.call("find", obj=f"{col} coffee mug")
    assert r.ok and r.data["found"] == "mug_1", (r.code, r.msg)
    p = ep.robot.call("pick", obj=f"{col} coffee mug")
    assert p.ok and w.robot.holding == "mug_1", (p.code, p.msg)


def test_packaging_noun_and_korean_description():
    ep = episode("senior_flat")
    w = ep.world
    ids = [o for o in sorted(w.objects) if w.objects[o].cls == "milk"]
    assert ids == ["milk_1"]
    assert detector_hits(w, "milk pack") == ids and detector_hits(w, "우유 팩") == ids
    assert "milk_1" not in detector_hits(w, "milk glass")


def test_pill_bottle_synonym_hits_only_the_medicine_bottle():
    """Round 10 (KO 014): "orange pill bottle" (the common name; BEHAVIOR-1K synset pill_bottle.n.01) named the
    orange medicine bottle but the camera knew only "medicine bottle". "pill box" stays the pill organizer."""
    ep = episode("senior_flat")
    w = ep.world
    assert w.objects["medicine_bottle_2"].attrs["color"] == "orange"
    assert detector_hits(w, "orange pill bottle") == ["medicine_bottle_2"]
    assert detector_hits(w, "pill bottle") == ["medicine_bottle_1", "medicine_bottle_2"]
    assert ep.robot._resolve_obj("orange pill bottle") == "medicine_bottle_2"
    pb = [o for o in w.objects if w.objects[o].cls == "pill_box"]
    hits = detector_hits(w, "pill box")
    assert hits == sorted(pb)
    assert not set(hits) & {"medicine_bottle_1", "medicine_bottle_2"}
    assert detector_hits(w, "medicine bottle") == ["medicine_bottle_1", "medicine_bottle_2"]


def test_english_plural_inflection_is_the_same_name():
    """r11 n50 gate (hl-dev-000024): the task says "vitamin bottle", the catalog alias is "vitamins"; find("vitamin") was
    `absent` with no event. An English query word matches a name word that differs only by the regular plural
    (-s, -es, -ies); a general rule, so "mugs" / "mug" and "shelves"-like regular forms work for every object."""
    from homeloop_robot.episode import make_episode
    from homeloop_robot.world import stem_en
    ep = make_episode("family_house", 4436, "ideal", 0, lang="en", user_spec={"persona": "child_present"}, key="s1")
    w = ep.world
    assert detector_hits(w, "vitamin") == ["vitamins_1"]
    assert detector_hits(w, "vitamins") == ["vitamins_1"]
    assert detector_hits(w, "vitamin bottle") == ["vitamins_1"]
    assert w.resolve_object("vitamin", None) == "vitamins_1"
    assert ep.robot._resolve_obj("vitamin") == "vitamins_1"
    assert detector_hits(w, "vitamin rack") == []
    assert [stem_en(x) for x in ("mugs", "boxes", "batteries", "glass", "bus", "gas")] == \
        ["mug", "box", "battery", "glass", "bus", "gas"]
    ep.robot.call("move", target=w.objects["vitamins_1"].at)
    r = ep.robot.call("find", obj="vitamin")
    assert r.ok and r.data["found"] == "vitamins_1", (r.code, r.msg)


def test_plural_packaging_noun_in_a_description():
    ep = episode("senior_flat")
    assert detector_hits(ep.world, "milk packs") == ["milk_1"] and detector_hits(ep.world, "milk pack") == ["milk_1"]
