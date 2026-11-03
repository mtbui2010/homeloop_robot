"""Pilot round 4: robot_agent's Announcer takes the plan milestones ("Task completed", "Task failed", step narration)
from the robot's i18n and falls back to its core table (English and Vietnamese only). The adapter had only
cannot_do / done / which_one, so a Korean user heard "Task completed" at the end of every KO episode (KO
hl-dev-000013 / 000001, rounds 1-4). Every milestone and the verbs of the robot's actions now have a Korean
phrase; English is unchanged (robot_agent's own table)."""
import pytest

from helpers import HAS_RA

pytestmark = pytest.mark.skipif(not HAS_RA, reason="robot_agent not importable")


def _announcer(lang):
    from robot_agent.core.planning.announcer import Announcer
    from homeloop_robot.configs.adapter import make_adapter
    ad = make_adapter()
    return Announcer(lang=lang, speak_backend=False, i18n=ad.i18n, quiet=ad.quiet_skills)


def _hangul(s):
    return any(0xAC00 <= ord(c) <= 0xD7A3 for c in s)


def test_every_core_milestone_has_a_korean_phrase():
    from robot_agent.core.planning.announcer import PHRASES as CORE
    from homeloop_robot import intent
    a = _announcer("ko")
    assert a.lang == "ko"
    for kind in CORE["en"]:
        text = a.say_for(kind, action="Pick", object="컵", reason="")
        if kind == "plan_ready":             # never spoken (robot_agent SILENT_KINDS)
            assert text == ""
            continue
        assert _hangul(text) and intent.in_lang(text, "ko"), (kind, text)
    assert a.say_for("done_success") == "작업을 완료했습니다"
    assert a.say_for("done_fail") == "작업에 실패했습니다"


@pytest.mark.parametrize("action", ["MoveTo", "Find", "Pick", "Place", "PutIn", "Open", "Close", "Handover", "Look",
                                    "Dock", "move", "find", "pick", "place", "put_in", "open", "close", "handover"])
def test_robot_actions_have_korean_verbs(action):
    text = _announcer("ko").say_for("step_start", action=action, object="컵")
    assert text.startswith("컵 ") and text.endswith("진행합니다"), text
    assert all(ord(c) < 128 or _hangul(c) for c in text) and not any(c.isascii() and c.isalpha() for c in text), text


def test_english_is_unchanged():
    a = _announcer("en")
    assert a.say_for("done_success") == "Task completed"
    assert a.say_for("done_fail") == "Task failed"
    assert a.say_for("step_start", action="Pick", object="cup") == "I will pick cup"
