"""R2-6 H1: Say / Announce are spoken in the language of their text. robot_agent passes ``lang`` only to Ask,
so a Korean message arrived with the manifest default "en" and never counted as said to a Korean listener
(hl-dev-000040). The bench test tests/test_say_lang_ra.py runs a KO message task through the real AssistLoop."""
import pytest

from homeloop_robot.configs import ra_skills
from homeloop_robot.configs.backend import reset_backend, set_backend
from homeloop_robot.episode import make_episode


@pytest.mark.parametrize("text,given,want", [
    ("점심 준비됐어요, 아빠.", None, "ko"),
    ("점심 준비됐어요, 아빠.", "en", "ko"),          # what robot_agent's default sent
    ("Lunch is ready, dad.", None, "en"),
    ("Lunch is ready, dad.", "ko", "en"),           # an English sentence is English in a Korean episode too
    ("12:30", "ko", "ko"),                          # no script: the given language
])
def test_speech_lang(text, given, want):
    assert ra_skills.speech_lang(text, given) == want


def test_no_script_falls_back_to_the_episode_language():
    ep = make_episode("senior_flat", 0, "ideal", 0, lang="ko", key="say-lang")
    set_backend(ep.robot)
    try:
        assert ra_skills.speech_lang("12:30") == "ko"
    finally:
        reset_backend()


@pytest.mark.parametrize("fn", [ra_skills.say, ra_skills.announce])
def test_say_records_the_text_language(fn):
    ep = make_episode("senior_flat", 0, "ideal", 0, lang="ko", key="say-lang")
    set_backend(ep.robot)
    try:
        assert fn(None, inputs="점심 준비됐어요.")["isdone"]
        assert fn(None, inputs="Lunch is ready.", lang="ko")["isdone"]
    finally:
        reset_backend()
    langs = [u.lang for u in ep.world.utterances if u.skill in ("say", "announce")]
    assert langs == ["ko", "en"]
