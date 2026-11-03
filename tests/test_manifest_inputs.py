"""Gate pilot round 1 (hl-dev-000028 KO): the Wait skill declared its input as [string, number] and was described as
"Wait a number of seconds", and SAGE planned {"action": "Wait", "object": 5}; robot_agent's planner reads every step
object as text and crashed ("'int' object has no attribute 'strip'"). Every skill's ``inputs`` (the step object) is
text; other parameters (Ask's ``retries``) are not planned by the LLM."""
from pathlib import Path

import yaml

import homeloop_robot.configs as cfg

MANIFEST_PATH = Path(cfg.__file__).with_name("manifest.yaml")       # (the adapter imports robot_agent)


def _skills():
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["skills"]


def test_every_skill_input_is_a_string():
    for sk in _skills():
        spec = ((sk.get("params") or {}).get("properties") or {}).get("inputs")
        if spec is not None:
            assert spec.get("type") == "string", (sk["name"], spec.get("type"))


def test_wait_says_its_seconds_are_text():
    wait = next(sk for sk in _skills() if sk["action"] == "Wait")
    assert "as text" in wait["description"] and "number of seconds" in wait["description"]
