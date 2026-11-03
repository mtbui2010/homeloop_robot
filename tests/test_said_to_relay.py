"""Pilot round 3 (homeloop_bench docs/experiments.md "Pilot rounds"), hl-dev-000013 KO: SAGE said the user's whole
(ASR-corrupted) request to the husband, '남편한테 갈서 10분 있다가 나간다고 맬해 주세요.' ("go to the husband and tell
him we leave in 10 minutes, please"). That is the request relayed word for word, addressed to the robot, not the
message, and said_to must not count it (R2-1: scoring stays strict). A message said to the person still counts."""
import pytest

from homeloop_robot.goals import holds
from homeloop_robot.types import Utterance
from homeloop_robot.world import from_house

ATOM = {"pred": "said_to", "args": ["partner_b", "leaving_soon"]}


def _said(text, lang):
    w = from_house("couple_flat", 0)
    w.lang = lang
    w.utterances.append(Utterance(t=0.0, skill="say", text=text, lang=lang, heard_by=("partner_b",)))
    return holds(ATOM, w)


@pytest.mark.parametrize("text,lang", [
    ("남편한테 갈서 10분 있다가 나간다고 맬해 주세요.", "ko"),          # the pilot utterance (ASR-corrupted request)
    ("남편한테 가서 10분 있다가 나간다고 말해 주세요.", "ko"),
    ("남편에게 10분 뒤에 출발한다고 전해 주세요.", "ko"),
    ("Let my husband know we're leaving in ten minutes, please.", "en"),
    ("Go to your husband and tell him we leave in ten minutes, please.", "en"),
    ("남편한테 가셔서 10분 있다가 나간다고 말씀드릴게요.", "ko"),        # an announcement of the telling
])
def test_relayed_request_is_not_the_message(text, lang):
    assert not _said(text, lang)


@pytest.mark.parametrize("text,lang", [
    ("10분 뒤에 출발해요.", "ko"),
    ("10분 있다가 나간다고 하셨어요.", "ko"),
    ("여보, 10분 있다가 나가요.", "ko"),
    ("We are leaving in ten minutes.", "en"),
    ("Your wife says we are leaving in ten minutes.", "en"),
])
def test_message_to_the_person_counts(text, lang):
    assert _said(text, lang)


def test_relay_to_another_person_named_in_the_message_still_counts():
    # the person named as listener is someone else (the message is about telling the wife): it is said to the husband
    w = from_house("couple_flat", 0)
    w.lang = "en"
    w.utterances.append(Utterance(t=0.0, skill="say", text="We are leaving in ten minutes, tell your wife too.",
                                  lang="en", heard_by=("partner_b",)))
    assert holds(ATOM, w)


@pytest.mark.parametrize("text,lang", [("남편한테 전화 왔어요.", "ko"), ("There is a phone call for my husband.", "en")])
def test_a_message_that_names_its_listener_is_delivered(text, lang):
    # naming the listener with a dative is not a relayed request when nothing asks to tell them
    w = from_house("couple_flat", 0)
    w.lang = lang
    w.utterances.append(Utterance(t=0.0, skill="say", text=text, lang=lang, heard_by=("partner_b",)))
    assert holds({"pred": "said_to", "args": ["partner_b", "phone_call"]}, w)
