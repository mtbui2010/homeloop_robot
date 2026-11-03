"""planner/seed_memory.jsonl: the seed pool SAGE retrieves from (manifest ``planner.seed_memory``; R2-7b).

10-12 solved examples in the format robot_agent's memory reads (task, reasoning, plan_text, verified, source), EN
and KO, written for the example house ``example_flat`` (homeloop_bench's progprompt example house, used by no
split). They cover delivery to a person (a surface beside them, and a handover), open before pick, a message, a
refusal and a multi-step task. Every plan passes embodiplan's action model with this robot's plan actions. The
bench runs each plan on the mock robot in example_flat and checks its goal, and checks that no example leaks a
dev / test task (homeloop_bench tests/test_seed_pool_leak.py)."""
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1] / "homeloop_robot"
MANIFEST = ROOT / "configs" / "manifest.yaml"
SEED = ROOT / "planner" / "seed_memory.jsonl"
SHOWS = ("fetch to a person: a reachable surface beside them", "fetch to a person: handover",
         "open before pick", "a message", "decline an unsafe request", "multi-step")


@pytest.fixture(scope="module")
def manifest():
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def episodes():
    return [json.loads(line) for line in SEED.read_text(encoding="utf-8").splitlines() if line.strip()]


def _steps(rec):
    return json.loads(rec["plan_text"])["steps"]


def test_manifest_points_at_the_seed_file(manifest):
    rel = manifest["planner"]["seed_memory"]
    assert (MANIFEST.parent / rel).resolve() == SEED.resolve()


def test_packaged():
    text = (ROOT.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert '"planner/*.jsonl"' in text


def test_seed_is_small_well_formed_and_bilingual(episodes):
    assert 10 <= len(episodes) <= 12
    tasks = [e["task"] for e in episodes]
    assert len(set(tasks)) == len(tasks)
    for e in episodes:
        assert e["task"].strip() and e["reasoning"].strip() and e["verified"] is True and e["source"] == "seed"
        assert e["house"] == "example_flat" and e["goal"]["all"]
        assert all(s.get("action") and s.get("object") for s in _steps(e))
        assert "plan" not in e and "steps" not in e          # the plan is plan_text only (memory_tools.plan_steps)
        hangul = any("가" <= ch <= "힣" for ch in e["task"])
        assert hangul == (e["lang"] == "ko")
    langs = [e["lang"] for e in episodes]
    assert langs.count("en") >= 4 and langs.count("ko") >= 4


def test_coverage(episodes):
    for want in SHOWS:
        assert any(e["shows"].startswith(want) for e in episodes), want
    acts = [{s["action"] for s in _steps(e)} for e in episodes]
    assert any("Handover" in a for a in acts) and any("Say" in a for a in acts)
    assert any({"Open", "Pick"} <= a for a in acts)
    # a delivery to a reachable surface is a Place on the person (ra_skills.place: the surface beside them)
    assert any(s["action"] == "Place" and s["object"] == "resident" for e in episodes for s in _steps(e))
    assert any(e["goal"].get("refuse") for e in episodes)


def test_the_robot_package_reports_the_pool():
    rv = pytest.importorskip("robot_agent.core.planning.robot")
    assert Path(rv.RobotView.load("homeloop_robot").seed_memory()) == SEED.resolve()


def test_every_plan_passes_the_action_model(episodes, manifest):
    pytest.importorskip("embodiplan")
    rv = pytest.importorskip("robot_agent.core.planning.robot")
    from embodiplan.action_model import Capabilities, simulate
    from embodiplan.memory_retriever import load_seed_examples
    from embodiplan.memory_tools import start_state
    actions = rv.RobotView.load("homeloop_robot").plan_actions
    for e in episodes:
        rep = simulate(_steps(e), initial_state=start_state(e),
                       capabilities=Capabilities.from_any(manifest["capabilities"]), actions=actions)
        assert rep.ok, (e["task"], rep.violations)
    # SAGE's loader reads every example (none dropped for its format)
    assert len(load_seed_examples(str(SEED))) == len(episodes)
