"""Structured robot questions (R2-7a, docs/user_model.md "Structured questions"): the user answers a question with
a meaning ({qtype, slots}) from the task script by qtype and slots; free text goes rules -> classifier; the
correctness mix, silence and ASR still apply; every answer records its path."""
import collections
import math
import re
from pathlib import Path

import pytest

from homeloop_robot import intent
from homeloop_robot.dialog import GoalView
from homeloop_robot.episode import make_episode
from homeloop_robot.world import from_house

HOUSE = "korean_apt_59"
DOCS = Path(__file__).resolve().parents[1] / "docs" / "user_model.md"

GLASS_SPEC = {"persona": "adult", "slot": "object", "intended": "mug_2",
              "candidates": [{"id": "mug_1", "mentions": {"en": ["white mug", "white one"], "ko": ["하얀 머그컵", "하얀 거"]}},
                             {"id": "mug_2", "mentions": {"en": ["green mug", "green one"], "ko": ["초록색 머그컵", "초록색 거"]}}],
              "answer": {"en": "The green one, please.", "ko": "초록색 거요."}}
GLASS_GOAL = {"all": [{"pred": "delivered", "args": ["mug_2", "user"], "mode": "reach", "mode_reason": None}]}
GLASS_REQ = {"en": "Could you bring me a mug?", "ko": "머그컵 좀 갖다줄래요?"}
MILK_SPEC = {"persona": "adult", "slot": "destination", "intended": "kimchi_fridge@kitchen",
             "candidates": [{"id": "fridge@kitchen", "mentions": {"en": ["fridge", "refrigerator"], "ko": ["냉장고"]}},
                            {"id": "kimchi_fridge@kitchen", "mentions": {"en": ["kimchi fridge"],
                                                                         "ko": ["김치냉장고", "김치 냉장고"]}}],
             "answer": {"en": "In the kimchi fridge, please.", "ko": "김치냉장고요."}}
MILK_GOAL = {"all": [{"pred": "in", "args": ["kimchi_box_1", "kimchi_fridge@kitchen"]}]}
MILK_REQ = {"en": "Put the kimchi box away, please.", "ko": "김치통 좀 넣어 주세요."}
FETCH_GOAL = {"all": [{"pred": "on", "args": ["remote_1", "tv_stand@living"]},
                      {"pred": "said_to", "args": ["grandpa", "dinner_ready"]}]}
FETCH_REQ = {"en": "Put the remote on the TV stand and tell Grandpa dinner is ready.",
             "ko": "리모컨을 TV대 위에 놓고 할아버지한테 저녁 준비됐다고 말해 주세요."}


def _user(L, spec, goal, req, profile="ideal", seed=0, classifier=None):
    ep = make_episode(HOUSE, 0, profile, seed, lang=L, user_spec=spec, key=f"structured|{seed}")
    u = ep.user
    u.hear_instruction(req[L], L)
    u.set_wants(goal)
    u.classifier = classifier
    return ep, u


def _ask(L, q, meaning, spec=None, goal=FETCH_GOAL, req=FETCH_REQ, **kw):
    ep, u = _user(L, spec if spec is not None else {"persona": "adult"}, goal, req, **kw)
    r, h = u.answer(q, L, tuple(ep.world.people["user"].pos), 1.0, meaning=meaning)
    return r, u.log[-1]


# ------------------------------------------------------------------------------------ the frozen list
def test_qtype_list_is_frozen_in_the_docs():
    text = DOCS.read_text(encoding="utf-8")
    sec = text.split("## Structured questions", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| `([a-z_]+)` \|", sec, re.M)
    assert tuple(rows) == intent.QTYPES
    assert intent.QTYPES == ("which_object", "which_place", "confirm", "where_are_you", "where_is", "repeat",
                             "did_you_mean", "what_to_say", "help", "free")


@pytest.mark.parametrize("m,ok", [
    ({"qtype": "which_object", "options": ["a", "b"]}, True),
    ({"qtype": "where_is"}, False),                       # obj is required
    ({"qtype": "did_you_mean", "word": "kitchen"}, True),
    ({"qtype": "dance"}, False),
    ("which_object", False),
    ({"qtype": "which_place", "options": "sink", "bogus": 1}, True),
])
def test_clean(m, ok):
    c = intent.clean(m)
    assert (c is not None) == ok
    if c is not None:
        assert set(c) <= {"qtype", *intent.SLOTS[c["qtype"]]}


# ------------------------------------------------------------------------------------ answers by qtype
@pytest.mark.parametrize("L", ["en", "ko"])
def test_which_object_gives_the_intended_candidate(L):
    q = {"en": "Which one should I bring?", "ko": "어느 쪽 말씀이세요? 하얀 머그컵, 아니면 초록색 머그컵?"}[L]
    r, log = _ask(L, q, {"qtype": "which_object", "options": ["white mug", "green mug"]}, GLASS_SPEC, GLASS_GOAL,
                  GLASS_REQ)
    assert log["path"] == "structured" and log["qtype"] == "which_object"
    assert r.text == GLASS_SPEC["answer"][L] and log["why"] == "clarify_answer"


@pytest.mark.parametrize("L", ["en", "ko"])
def test_which_place_gives_the_intended_destination(L):
    q = {"en": "Fridge or kimchi fridge?", "ko": "냉장고요, 김치냉장고요?"}[L]
    r, log = _ask(L, q, {"qtype": "which_place", "options": ["fridge", "kimchi fridge"]}, MILK_SPEC, MILK_GOAL,
                  MILK_REQ)
    assert r.text == MILK_SPEC["answer"][L] and log["path"] == "structured"


@pytest.mark.parametrize("L,txt", [("en", "On the TV stand, please."), ("ko", "티비장 위에")])
def test_which_place_with_an_object_is_its_destination(L, txt):
    # in a Korean episode the meaning counts when the Korean text heard reads the same way (structured_mismatch)
    r, log = _ask(L, {"en": "?", "ko": "리모컨 어디에 둘까요?"}[L], {"qtype": "which_place", "obj": "remote"})
    assert log["why"] == "goal_destination" and txt in r.text


@pytest.mark.parametrize("L", ["en", "ko"])
def test_confirm_read_back(L):
    good = "I will put the remote on the TV stand, then say \"Dinner is ready.\" to grandpa."
    bad = "I will put the remote on the coffee table, then say \"Dinner is ready.\" to grandpa."
    q = "그렇게 할게요. 맞죠?" if L == "ko" else "OK?"
    r, log = _ask(L, q, {"qtype": "confirm", "goal": good})
    assert r.kind == "yes" and log["why"] == "goal_confirm"
    r, log = _ask(L, q, {"qtype": "confirm", "goal": bad})
    assert r.kind == "no" and log["why"] == "goal_correct"


@pytest.mark.parametrize("L", ["en", "ko"])
def test_confirm_one_candidate(L):
    r, _ = _ask(L, {"en": "?", "ko": "초록색 머그컵 맞아요?"}[L], {"qtype": "confirm", "obj": "green mug"}, GLASS_SPEC,
                GLASS_GOAL, GLASS_REQ)
    assert r.kind == "yes"
    r, _ = _ask(L, {"en": "?", "ko": "하얀 머그컵 맞아요?"}[L], {"qtype": "confirm", "obj": "white mug"}, GLASS_SPEC,
                GLASS_GOAL, GLASS_REQ)
    assert r.kind == "no" and r.text.endswith(GLASS_SPEC["answer"][L][1:] if L == "ko" else "green one, please.")


@pytest.mark.parametrize("L,where", [("en", "sofa"), ("ko", "소파")])
def test_where_are_you(L, where):
    r, log = _ask(L, {"en": "?", "ko": "지금 어디 계세요?"}[L], {"qtype": "where_are_you"})
    assert where in r.text and log["why"] == "self_position"


@pytest.mark.parametrize("L,obj,txt", [("en", "remote", "coffee table"), ("ko", "리모컨", "거실 탁자"),
                                       ("en", "grandpa", "bed"), ("ko", "할아버지", "침대")])
def test_where_is_object_or_person(L, obj, txt):
    q = {"리모컨": "리모컨 어디 있어요?", "할아버지": "할아버지 어디 계세요?"}.get(obj, "?")
    r, log = _ask(L, q, {"qtype": "where_is", "obj": obj})
    assert txt in r.text and log["why"] in ("location", "person_location")


@pytest.mark.parametrize("L", ["en", "ko"])
def test_repeat_and_did_you_mean(L):
    r, log = _ask(L, {"en": "?", "ko": "다시 말씀해 주시겠어요?"}[L], {"qtype": "repeat"})
    assert r.text == FETCH_REQ[L] and log["why"] == "repeat_request"
    word = {"en": "TV stand", "ko": "할아버지"}[L]
    r, log = _ask(L, {"en": "?", "ko": "할아버지라고 하셨어요?"}[L], {"qtype": "did_you_mean", "word": word})
    assert r.kind == "yes" and r.text.endswith(FETCH_REQ[L]) and log["why"] == "repair_confirm"


@pytest.mark.parametrize("L,txt", [("en", "Dinner is ready."), ("ko", "저녁 준비됐어요.")])
def test_what_to_say_is_the_message(L, txt):
    r, log = _ask(L, {"en": "?", "ko": "할아버지께 뭐라고 말씀드릴까요?"}[L], {"qtype": "what_to_say", "person": "grandpa"})
    assert txt in r.text and log["why"] == "goal_message"


def test_structured_free_and_unknown_fall_back_to_rules():
    r, log = _ask("en", "Where are you?", {"qtype": "free"})
    assert log["path"] == "rules" and log["qtype"] == "where_are_you"
    r, log = _ask("en", "Where are you?", {"qtype": "nonsense"})
    assert log["path"] == "rules"


def test_structured_beats_a_misleading_korean_text():
    """knowno_like's Korean question "어느 쪽 말씀이세요? ..." contains 말씀이세요 (an ASR-repair cue for the rules);
    with its meaning the user answers the choice."""
    q = "어느 쪽 말씀이세요? 하얀 머그컵, 아니면 초록색 머그컵?"
    r, log = _ask("ko", q, {"qtype": "which_object", "options": ["하얀 머그컵", "초록색 머그컵"]}, GLASS_SPEC, GLASS_GOAL,
                  GLASS_REQ)
    assert r.text == GLASS_SPEC["answer"]["ko"]


# ------------------------------------------------------------------------------------ rules -> classifier
class Clf:
    def __init__(self, out):
        self.out, self.calls = out, []

    def __call__(self, q, lang):
        self.calls.append((q, lang))
        return self.out


def test_classifier_only_when_the_rules_do_not_understand():
    clf = Clf({"qtype": "what_to_say", "person": "grandpa"})
    r, log = _ask("en", "Where are you?", None, classifier=clf)
    assert clf.calls == [] and log["path"] == "rules"
    r, log = _ask("en", "Any particular words you want me to use for him?", None, classifier=clf)
    assert len(clf.calls) == 1 and log["path"] == "llm" and log["qtype"] == "what_to_say"
    assert r.text == "Dinner is ready."


def test_classifier_free_or_garbage_keeps_not_sure():
    for out in ({"qtype": "free"}, None, {"qtype": "zzz"}):
        r, log = _ask("en", "Any particular words you want me to use for him?", None, classifier=Clf(out))
        assert log["path"] == "llm" and r.kind == "not_sure" and log["qtype"] == "free"


def test_no_classifier_is_rules_only():
    r, log = _ask("en", "Any particular words you want me to use for him?", None)
    assert log["path"] == "rules" and log["qtype"] == "free" and r.kind == "not_sure"


# ------------------------------------------------------------------------------------ mix, silence, ASR unchanged
def _rate_ok(k, n, p):
    sd = math.sqrt(max(p * (1 - p), 1e-9) / n)
    return abs(k / n - p) <= 4 * sd + 1e-9


@pytest.mark.parametrize("L", ["en", "ko"])
def test_mix_and_silence_unchanged_for_structured_questions(L):
    ep, u = _user(L, GLASS_SPEC, GLASS_GOAL, GLASS_REQ, profile="real")
    u.patience = 10 ** 6
    xy = tuple(ep.world.people["user"].pos)
    kinds = collections.Counter()
    heard_diff = 0
    n = 6000
    for _ in range(n):
        q = {"en": "?", "ko": "하얀 머그컵이요, 초록색 머그컵이요?"}[L]
        r, h = u.answer(q, L, xy, 0.0, meaning={"qtype": "which_object", "options": ["white mug", "green mug"]})
        kinds[r.kind] += 1
        heard_diff += r.kind != "no_answer" and h.text != r.text
        u.log.clear()
    answered = n - kinds["no_answer"]
    assert _rate_ok(kinds["no_answer"], n, u.p_no_answer)
    assert _rate_ok(kinds["wrong"], answered, u.p_wrong)
    assert _rate_ok(kinds["not_sure"], answered, u.p_not_sure)
    assert heard_diff > 0                                   # ASR noise applies to structured answers


def test_meaning_does_not_change_the_outcome_draws():
    """The ask's outcome draws and the user's streams do not depend on the meaning: the same rules-understood
    question with and without its meaning gives the same reply, latency and heard text."""
    out = []
    for m in (None, {"qtype": "where_are_you"}):
        ep = make_episode(HOUSE, 0, "real", 3, lang="en", user_spec={"persona": "adult"}, key="same")
        args = {"question": "Where are you?", "lang": "en"}
        if m:
            args["meaning"] = m
        res = [ep.robot.call("ask", **args) for _ in range(5)]
        out.append([(r.ok, r.code, r.duration_s, (r.data or {}).get("answer")) for r in res])
        assert all((r.truth or {}).get("intent", {}).get("path") in (None, "structured" if m else "rules")
                   for r in res)
    assert out[0] == out[1]


def test_help_meaning_counts_as_a_help_request():
    """A structured help question is a help request: with a help-clearable fault the user says they moved it."""
    from homeloop_robot.skills import Robot  # noqa: F401 - the robot core handles help faults
    ep, u = _user("en", {"persona": "adult"}, FETCH_GOAL, FETCH_REQ)
    u.help_request("Could you give me a hand?", 0.0)
    r, h = u.answer("Could you give me a hand?", "en", tuple(ep.world.people["user"].pos), 0.0,
                    meaning={"qtype": "help"})
    assert r.text == "OK, I moved it." and u.log[-1]["path"] == "structured" and u.log[-1]["qtype"] == "help"


def test_bad_meaning_type_is_a_software_error():
    ep = make_episode(HOUSE, 0, "ideal", 0, lang="en", user_spec={"persona": "adult"}, key="bad")
    r = ep.robot.call("ask", question="Where are you?", meaning="which_object")
    assert not r.ok and r.code.value == "software"


def test_compound_read_back_by_text_names_another_part_s_place():
    """A read-back that names the place of another part of the request (the TV stand for the remote) still
    confirms the message to grandpa (GoalView._person_ok), by text (rules) as by meaning."""
    q = "I will put the remote on the TV stand, then say \"Dinner is ready.\" to grandpa. Is that right?"
    r, log = _ask("en", q, None)
    assert log["path"] == "rules" and r.kind == "yes" and log["why"] == "goal_confirm"
    q = "I will put the remote on the TV stand, then say \"Dinner is ready.\" to grandpa at the sofa. Is that right?"
    r, log = _ask("en", q, None)
    assert r.kind == "no"                   # grandpa is in bed, not at the sofa
