"""Pilot round 2 (hl-dev-000013 KO): one-syllable Korean person names (나, 저, 애, 딸) are written to the ENV in their
dative forms, because robot_agent matches a non-ASCII place phrase as a plain substring: '나' was "mentioned" inside
'나간다고' and SAGE asked "You mentioned the 나. What should I do there?"."""
import pytest

from helpers import HAS_RA
from homeloop_robot.configs.tasks import env_alias_forms, env_for
from homeloop_robot.houses import list_houses
from homeloop_robot.world import from_house


def test_alias_forms():
    assert env_alias_forms("나") == ["나한테", "나에게", "내게"]
    assert env_alias_forms("저") == ["저한테", "저에게", "제게"]
    assert env_alias_forms("딸") == ["딸한테", "딸에게"]
    assert env_alias_forms("남편") == ["남편"] and env_alias_forms("me") == ["me"] and env_alias_forms("") == []


def test_no_one_syllable_korean_alias_in_env():
    for h in list_houses():
        for k, e in env_for(from_house(h, 0)).items():
            for a in e["aliases"]:
                assert a.isascii() or len(a.replace(" ", "")) > 1, (h, k, a)
    env = env_for(from_house("couple_flat", 0))
    speaker = next(e for e in env.values() if e.get("person") == "partner_a")
    assert {"저한테", "제게", "나에게", "와이프", "아내"} <= set(speaker["aliases"])


@pytest.mark.skipif(not HAS_RA, reason="robot_agent not importable")
@pytest.mark.parametrize("text,person", [
    ("남편한테 가서 10분 있다가 나간다고 말해 주세요.", "partner_b"),          # the pilot task: only the husband
    ("오늘 저녁에 하나만 나중에 가져다주세요.", None),
    ("머그컵 좀 찾아서 저한테 가져다줄 수 있어요?", "partner_a"),
    ("머그컵 좀 제게 가져다주세요.", "partner_a"),
])
def test_robot_agent_mentions_only_real_person_names(text, person):
    from robot_agent.core.planning.assist_loop import Places
    from robot_agent.core.planning.understand import place_mentions
    env = env_for(from_house("couple_flat", 0))
    got = {env[k]["person"] for m in place_mentions(text, Places(env)) for k in m[3] if env[k].get("person")}
    assert got == ({person} if person else set()), (text, got)
