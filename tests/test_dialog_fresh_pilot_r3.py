"""Fresh pilot round 3 (homeloop_bench docs/experiments.md "Pilot rounds", results/pilot_r27x/round3):
- hl-dev-000060 KO: a "to me" word (the humble giving verb '드릴게요', '당신', "hand it") confirms a delivery to the
  speaker only in that object's own part of a compound read-back, with no other person and no place or room of
  another room said as where it goes there. '안경을 거실 탁자에 두고, 리모컨은 할아버지께 드릴게요' was "yes" for a speaker
  in the small room; the English equivalent was "no";
- hl-dev-000016 EN: a user unsure of the answer to a question it understood says "I don't know.", not the
  not-understood "I'm not sure what you mean."."""
import pytest

from homeloop_robot import dialog as D
from homeloop_robot.episode import make_episode

GRANDPA_GOAL = {"all": [{"pred": "delivered", "args": ["glasses_1", "user"], "mode": "reach", "mode_reason": None},
                        {"pred": "delivered", "args": ["remote_1", "grandpa"], "mode": "hand",
                         "mode_reason": "user_needs"}]}
GRANDPA_REQ = {"en": "Hey, bring me the glasses and then hand the remote to Grandpa.",
               "ko": "안경 좀 가져와 주실래요? 그리고 아버님께 리모컨 갖다 드릴 수 있을까요?"}
AT_060 = {"glasses_1": "tv_stand@living", "remote_1": "sofa@living"}
SEAT = "desk_chair@small"                    # the speaker sits in the small room


def _episode(L, house="korean_apt_59"):
    ep = make_episode(house, 0, "ideal", 0, lang=L, user_spec={"persona": "adult"}, key="fresh-r3")
    for o, p in AT_060.items():
        ep.world.objects[o].at = p
        ep.world.initial_at[o] = p
    ep.world.people[ep.world.user_id()].seat = SEAT
    return ep


def _ask(L, q, meaning=None):
    ep = _episode(L)
    u = ep.user
    u.hear_instruction(GRANDPA_REQ[L], L)
    u.set_wants(GRANDPA_GOAL)
    r, _h = u.answer(q, L, tuple(ep.world.people[ep.world.user_id()].pos), 1.0, meaning=meaning)
    return r, u.log[-1]


# the stored sage_norag KO read-back (call k=3, path structured, answered "yes") and the probes of the round
STORED_KO = ("TV 스탠드에 있는 안경은 거실에 바로 올려서 당신이 쉽게 достать 수 있게 할게요. 그리고 당신이 쉽게 достать 수 있는 곳에 "
             "있는 리모컨은 할아버지께 올려줄게요. 맞죠?")
STORED_EN = ("I will put the 안경 from the tv_stand in the living on the spot within your reach, then put the 리모컨 from "
             "the spot within your reach on the grandpa.")
WRONG = [
    ("ko", "TV 스탠드에 있는 안경을 거실 탁자에 두고, 리모컨은 할아버지께 드릴게요. 맞죠?"),
    ("ko", "TV 스탠드에 있는 안경을 거실 소파에 두고, 리모컨은 할아버지께 드릴게요. 맞죠?"),
    ("ko", "TV 스탠드에 있는 안경은 거실에 둘게요. 리모컨은 할아버지께 드릴게요. 맞죠?"),
    ("ko", STORED_KO),
    ("en", "I will put the glasses from the TV stand on the coffee table, then give the remote to grandpa. "
           "Is that right?"),
    ("en", "I will put the glasses from the TV stand on the sofa, then hand it to grandpa with the remote. "
           "Is that right?"),
]
RIGHT = [
    ("ko", "TV 스탠드에 있는 안경을 가져와서 드리고, 리모컨은 할아버지께 드릴게요. 맞죠?"),
    ("ko", "거실 TV 스탠드에 있는 안경을 갖다 드리고, 리모컨은 할아버지께 드릴게요. 맞죠?"),
    ("ko", "안경을 당신 손이 닿는 곳에 두고, 리모컨은 할아버지께 건네 드릴게요. 맞죠?"),
    ("ko", "안경을 작은방 책상에 두고 드릴게요. 그리고 리모컨은 할아버지께 드릴게요. 맞죠?"),
    ("en", "I will bring the glasses from the TV stand in the living room to you, then give the remote to grandpa. "
           "Is that right?"),
    ("en", "I'll bring you the glasses, then hand the remote to grandpa. Is that right?"),
    ("en", "I will put the glasses on the spot within your reach, then hand the remote to grandpa. Is that right?"),
]


@pytest.mark.parametrize("L,q", WRONG)
def test_another_parts_to_me_word_does_not_confirm_the_speakers_delivery(L, q):
    r, log = _ask(L, q)
    assert r.kind == "no" and ("glasses" in r.text or "안경" in r.text), (r.text, log)


def test_stored_read_back_with_its_meaning_is_not_confirmed():
    r, log = _ask("ko", STORED_KO, {"qtype": "confirm", "goal": STORED_EN})
    assert r.kind == "no" and "안경" in r.text, (r.text, log)


@pytest.mark.parametrize("L,q", RIGHT)
def test_a_to_me_word_in_the_objects_own_part_still_confirms(L, q):
    r, log = _ask(L, q)
    assert r.kind == "yes", (r.text, log)


def test_object_parts():
    ep = _episode("ko")
    ep.user.set_wants(GRANDPA_GOAL)
    gv = D.GoalView(ep.world, ep.user.wants, ep.world.user_id(), lambda pid: SEAT)
    q = "TV 스탠드에 있는 안경을 가져와서 드리고, 리모컨은 할아버지께 드릴게요. 맞죠?"
    assert [p.strip() for p in gv.object_parts(q, "glasses_1")] == ["TV 스탠드에 있는 안경을 가져와서", "드리고"]
    assert [p.strip() for p in gv.object_parts(q, "remote_1")] == ["리모컨은 할아버지께 드릴게요.", "맞죠?"]


def test_room_said_as_destination():
    w = _episode("en").world
    assert D.room_said_as_dest(w, "안경은 거실에 바로 올려서", "living")
    assert not D.room_said_as_dest(w, "거실에 있는 안경을", "living")
    assert not D.room_said_as_dest(w, "거실 TV 스탠드에 있는 안경을", "living")
    assert D.room_said_as_dest(w, "bring the glasses to the living room", "living")
    assert not D.room_said_as_dest(w, "go to the living room, then", "living")
    assert not D.room_said_as_dest(w, "the glasses from the TV stand in the living room to you", "living")


# ---- 016: unsure of the answer is not "not understood" -----------------------------------------------------------

@pytest.mark.parametrize("L", ["en", "ko"])
def test_unsure_answer_to_a_clear_question_is_dont_know(L):
    ep = _episode(L)
    u = ep.user
    u.hear_instruction(GRANDPA_REQ[L], L)
    u.set_wants(GRANDPA_GOAL)
    u.p_wrong, u.p_not_sure, u.p_no_answer = 0.0, 1.0, 0.0
    q = {"en": "Where are the glasses?", "ko": "안경은 어디에 있어요?"}[L]
    r, _h = u.answer(q, L, tuple(ep.world.people[ep.world.user_id()].pos), 1.0)
    assert r.kind == "not_sure" and r.text == D.TEXT["dont_know"][L], r.text


@pytest.mark.parametrize("L", ["en", "ko"])
def test_a_question_not_understood_is_still_not_sure_what_you_mean(L):
    ep = _episode(L)
    u = ep.user
    u.hear_instruction(GRANDPA_REQ[L], L)
    u.set_wants(GRANDPA_GOAL)
    u.p_wrong, u.p_not_sure, u.p_no_answer = 0.0, 0.0, 0.0
    q = {"en": "I will go now.", "ko": "이제 갈게요."}[L]
    r, _h = u.answer(q, L, tuple(ep.world.people[ep.world.user_id()].pos), 1.0)
    assert r.kind == "not_sure" and r.text == D.TEXT["not_sure"][L], r.text
