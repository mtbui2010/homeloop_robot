from pathlib import Path

import pytest

from helpers import HAS_RA, episode
from homeloop_robot.configs import ra_skills
from homeloop_robot.configs.backend import reset_backend, set_backend
from homeloop_robot.configs.tasks import ENV, env_for

PKG = Path(__file__).resolve().parents[1] / "homeloop_robot"


def test_env_shape():
    assert "counter@kitchen" in ENV
    e = ENV["fridge@kitchen"]
    assert set(e) == {"loc", "height", "default_mode", "aliases", "openable"} and e["openable"] is True
    assert "냉장고" in e["aliases"]
    assert set(env_for(episode("family_house").world)) >= {"dock@living", "fridge@kitchen"}


def test_ra_skills_legacy_dicts():
    ep = episode()
    set_backend(ep.robot)
    try:
        assert ra_skills.move(None, inputs="counter@kitchen")["isdone"] is True
        f = ra_skills.find(None, inputs="red mug")
        assert f["isdone"] and f["found"] == "red mug" and "red mug" in f["ins"]   # names, not world ids
        assert ra_skills.pick(None, inputs="mug_1")["isdone"]
        assert ra_skills.grasp_check(None)["isdone"] is True
        p = ra_skills.pose(None)
        assert isinstance(p["pose"], tuple) and len(p["pose"]) == 3
        bad = ra_skills.place(None, inputs="fridge@kitchen")
        assert bad["isdone"] is False and bad["code"] == "unreachable"
        a = ra_skills.ask(None, inputs="Where?", retries=1)
        assert a["isdone"] is False and a["text"] == "" and a["code"] == "timeout"
        assert ra_skills.wait(None, inputs="3")["isdone"]
    finally:
        reset_backend()


@pytest.mark.skipif(not HAS_RA, reason="robot_agent not importable")
def test_check_manifest_strict():
    from robot_agent.contract.check_manifest import assert_manifest_matches
    assert_manifest_matches(PKG, strict=True)


@pytest.mark.skipif(not HAS_RA, reason="robot_agent not importable")
def test_adapter_bind_and_codes():
    from robot_agent.contract import FailureCode, Unbindable
    from homeloop_robot.configs.adapter import make_adapter
    ep = episode()
    set_backend(ep.robot)
    try:
        ad = make_adapter()
        assert ad.bind({"action": "MoveTo", "object": "KitchenCounter"}) == ("move", {"inputs": "counter@kitchen"})
        assert ad.bind({"action": "MoveTo", "object": "dock"}) == ("move", {"inputs": "dock@living"})
        assert ad.bind({"action": "Pick", "object": "red mug"}) == ("pick", {"inputs": "mug_1"})
        assert ad.bind({"action": "PutIn", "object": "fridge"}) == ("put_in", {"inputs": "fridge@kitchen"})
        assert ad.bind({"action": "Say", "object": "hi"}) == ("say", {"inputs": "hi"})
        assert ad.bind({"action": "Wait", "object": "3"}) == ("wait", {"inputs": "3"})
        assert ad.bind({"action": "Dock"}) == ("dock", {"inputs": "dock"})
        assert ad.bind({"action": "WaitForUnload"})[0] == "handover"
        for a in ("Observe", "Verify", "Fly"):
            with pytest.raises(Unbindable):
                ad.bind({"action": a, "object": "x"})
        name, params = ad.bind({"action": "Pick", "object": "mug_1"})
        out = getattr(ra_skills, name)(None, **params)
        assert FailureCode.parse(out["code"]) == FailureCode.ABSENT
        obs = ad.observe()
        assert obs.arrived == "dock@living" and obs.hands == {"right": None}
        assert ad.pose()["x"] == pytest.approx(ep.world.robot.pose[0])
        assert ad.health()["ok"] is True
        assert "cannot_do" in ad.i18n.phrases and ad.i18n.text("cannot_do", "ko")
    finally:
        reset_backend()


def test_env_aliases_resolve_copied_keys():
    from homeloop_robot.world import from_house
    env = env_for(from_house("studio_flat", 0))
    al = env["bath_cabinet@bathroom"]["aliases"]
    assert "bath cabinet@bathroom" in al
    assert not any(a.lower().startswith("bathroom bathroom") for k in env for a in env[k]["aliases"])


@pytest.mark.skipif(not HAS_RA, reason="robot_agent not importable")
def test_robot_agent_grounds_a_copied_key():
    from robot_agent.core.planning.assist_loop import Places
    from homeloop_robot.world import from_house
    places = Places(env_for(from_house("studio_flat", 0)))
    task = "Could you stash that gray towel in the bathroom cabinet?"
    assert places.candidates("bath_cabinet@bathroom", task) == ["bath_cabinet@bathroom"]
    assert places.ground("kitchen_sink@main", task) == "kitchen_sink@main"


def test_ra_skills_report_names_not_ids_and_dock_on_move():
    ep = episode()
    set_backend(ep.robot)
    try:
        assert ra_skills.move(None, inputs="bed@bedroom")["isdone"]
        f = ra_skills.find(None, inputs="red mug")
        assert f["isdone"] is False and "mug_1" not in f["msg"] and "red mug" in f["msg"]
        assert not ep.world.robot.docked
        m = ra_skills.move(None, inputs="dock@living")
        assert m["isdone"] and m["docked"] and ep.world.robot.docked
    finally:
        reset_backend()


def test_env_dock_aliases_name_charging():
    from homeloop_robot.world import from_house
    env = env_for(from_house("family_house", 0))
    assert {"charge", "충전"} <= set(env["dock@living"]["aliases"])
    env = env_for(from_house("shared_flat", 0))
    assert "room A bed in room A" not in env["bed@room_a"]["aliases"]
