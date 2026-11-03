"""The heard-text check (review round 1, docs/user_model.md "Heard-text check"): a planner's structured meaning
counts only when the text the user hears says it, in both languages: the same qtype, slots naming the same
things / places / people as the text, and a text in the user's language. Otherwise the user answers what it
heard (path structured_mismatch), so no answer comes through a channel a real user does not hear."""
import pytest

from homeloop_robot import intent
from homeloop_robot.episode import make_episode
from test_dialog_structured import FETCH_GOAL, FETCH_REQ, GLASS_GOAL, GLASS_REQ, GLASS_SPEC, HOUSE, _ask

REMOTE_GOAL = {"all": [{"pred": "on", "args": ["remote_1", "tv_stand@living"]}]}
REMOTE_REQ = {"en": "Put the remote on the TV stand.", "ko": "리모컨 티비장 위에 놔 주세요."}


def _remote_where(L):
    w = make_episode(HOUSE, 0, "ideal", 0).world
    from homeloop_robot import dialog as D
    return D.location_text(w, "remote_1", L), D.location_text(w, "apple_1", L)


# ------------------------------------------------------------------------------------ slots must match the text
@pytest.mark.parametrize("L,q", [("ko", "빨간 사과 어디 있어요?"), ("en", "Where is the red apple?")])
def test_where_is_another_object_than_the_meaning(L, q):
    """SAGE's question names the apple (a mistranslated entity in KO); its meaning says the remote. The user
    answers where the apple is, never where the remote is."""
    remote_at, apple_at = _remote_where(L)
    assert remote_at != apple_at
    r, log = _ask(L, q, {"qtype": "where_is", "obj": "remote"}, goal=REMOTE_GOAL, req=REMOTE_REQ)
    assert log["path"] == "structured_mismatch" and r.text != remote_at and r.text == apple_at, (r.text, log)
    # the same text without a meaning gives the same answer
    r2, _log = _ask(L, q, None, goal=REMOTE_GOAL, req=REMOTE_REQ)
    assert r2.text == r.text


@pytest.mark.parametrize("L,q", [("ko", "리모컨 어디 있어요?"), ("en", "Where is the remote?")])
def test_where_is_the_same_object_counts(L, q):
    r, log = _ask(L, q, {"qtype": "where_is", "obj": "remote"}, goal=REMOTE_GOAL, req=REMOTE_REQ)
    assert log["path"] == "structured" and r.text == _remote_where(L)[0]


@pytest.mark.parametrize("L,q", [("ko", "리모컨을 소파에 둘게요. 맞죠?"),
                                 ("en", "I will put the remote on the sofa. Is that right?")])
def test_read_back_with_another_place_than_the_meaning(L, q):
    """The heard read-back says the sofa, the meaning's read-back the TV stand: the user answers what it heard."""
    m = {"qtype": "confirm", "goal": "I will put the remote on the TV stand."}
    r, log = _ask(L, q, m, goal=REMOTE_GOAL, req=REMOTE_REQ)
    assert log["path"] == "structured_mismatch" and r.kind == "no", (r.text, log)


@pytest.mark.parametrize("L,q", [("ko", "싱크대요, 식탁이요?"), ("en", "The sink or the dining table?")])
def test_which_place_options_other_than_the_text(L, q):
    from test_dialog_structured import MILK_GOAL, MILK_REQ, MILK_SPEC
    r, log = _ask(L, q, {"qtype": "which_place", "options": ["fridge", "kimchi fridge"]}, MILK_SPEC, MILK_GOAL,
                  MILK_REQ)
    assert log["path"] == "structured_mismatch", (r.text, log)


def test_slots_agree():
    w = make_episode(HOUSE, 0, "ideal", 0).world
    assert not intent.slots_agree({"qtype": "where_is", "obj": "remote"}, "빨간 사과 어디 있어요?", w)
    assert intent.slots_agree({"qtype": "where_is", "obj": "remote"}, "리모컨 어디 있어요?", w)
    # a text naming nothing of that kind takes it from context
    assert intent.slots_agree({"qtype": "which_place", "obj": "remote"}, "어디에 둘까요?", w)
    assert intent.slots_agree({"qtype": "where_are_you"}, "Where are you?", w)
    assert intent.slots_agree({"qtype": "what_to_say", "person": "grandpa"}, "할아버지께 뭐라고 말씀드릴까요?", w)


# ------------------------------------------------------------------------------------ a meaning on unrelated text
UNRELATED = [
    ({"qtype": "what_to_say"}, FETCH_GOAL, FETCH_REQ, None),
    ({"qtype": "which_place", "obj": "remote"}, FETCH_GOAL, FETCH_REQ, None),
    ({"qtype": "confirm", "goal": "Put the remote on the sofa"}, FETCH_GOAL, FETCH_REQ, None),
    ({"qtype": "which_object"}, FETCH_GOAL, FETCH_REQ, None),
    ({"qtype": "where_are_you"}, FETCH_GOAL, FETCH_REQ, None),
    ({"qtype": "where_is", "obj": "remote"}, FETCH_GOAL, FETCH_REQ, None),
    ({"qtype": "which_object"}, GLASS_GOAL, GLASS_REQ, GLASS_SPEC),
]
TEXTS = {"en": ["Okay.", "...", "Beep.", "Hi"], "ko": ["네.", "...", "삐.", "안녕하세요"]}


@pytest.mark.parametrize("L", ["en", "ko"])
@pytest.mark.parametrize("k", range(len(UNRELATED)))
def test_meaning_on_unrelated_text_gets_no_scripted_answer(L, k):
    m, goal, req, spec = UNRELATED[k]
    for q in TEXTS[L]:
        r, log = _ask(L, q, m, spec if spec is not None else {"persona": "adult"}, goal, req)
        assert log["path"] == "structured_mismatch" and r.kind in ("not_sure",), (q, m, r.text, log)
        assert not r.text.startswith(("No, ", "아니요")) and "TV" not in r.text and "티비" not in r.text


# ------------------------------------------------------------------------------------ the user's language
@pytest.mark.parametrize("q,m", [
    ("Where are you? Which place should I bring it to?", {"qtype": "where_are_you"}),
    ("Where should I put the remote?", {"qtype": "which_place", "obj": "remote"}),
    ("I couldn't find the remote. Where is it?", {"qtype": "where_is", "obj": "remote"}),
    ("You mentioned the 할아버지. What should I do there?", {"qtype": "repeat", "about": "request"}),
])
def test_untranslated_english_in_a_korean_episode_is_a_mismatch(q, m):
    """robot_agent's _in_lang returns the English text when its translation call fails: a Korean user does not
    follow it, with or without a meaning."""
    r, log = _ask("ko", q, m)
    assert log["path"] == "structured_mismatch" and log["why"] == "not_in_lang" and r.kind == "not_sure"
    r, log = _ask("ko", q, None)
    assert log["path"] == "rules" and log["why"] == "not_in_lang" and r.kind == "not_sure"


def test_in_lang():
    assert intent.in_lang("리모컨 어디 있어요?", "ko") and intent.in_lang("TV 스탠드 위에 둘까요?", "ko")
    assert not intent.in_lang("Where is the remote?", "ko")
    assert intent.in_lang("Where is the remote?", "en") and intent.in_lang("Did you mean '김치냉장고'?", "en")
    assert not intent.in_lang("리모컨 어디 있어요?", "en")
    # mostly English with a Korean word of the request in it: still English
    assert not intent.in_lang("You mentioned the 남편. What should I do there?", "ko")
    assert intent.in_lang("김치냉장고는 주방에 있는 kimchi_fridge에 넣을게요. 맞죠?", "ko")
    assert intent.in_lang("...", "ko") and intent.in_lang("...", "en")


@pytest.mark.parametrize("L,text,ok", [("ko", "Dad, lunch is ready.", False), ("ko", "아빠, 점심 준비됐어요.", True),
                                       ("en", "Dad, lunch is ready.", True), ("en", "아빠, 점심 준비됐어요.", False)])
def test_said_to_needs_the_household_language(L, text, ok):
    """A message counts only in the household's language: "Dad, lunch is ready." said in English in a Korean home
    (KO hl-dev-000040) does not tell dad."""
    from homeloop_robot import goals as G
    from homeloop_robot.catalog import MESSAGES, message_matches
    from homeloop_robot.types import Utterance
    key = next(k for k in MESSAGES if message_matches(k, "Dad, lunch is ready.", "en")
               and message_matches(k, "아빠, 점심 준비됐어요.", "ko"))
    ep = make_episode(HOUSE, 0, "ideal", 0, lang=L)
    pid = sorted(ep.world.people)[0]
    ep.world.utterances.append(Utterance(t=0.0, skill="say", text=text, lang="ko" if intent._hangul(text) else "en",
                                         heard_by=(pid,)))
    assert G.holds({"pred": "said_to", "args": [pid, key]}, ep.world) == ok


# ------------------------------------------------------------------------------------ SAGE's English templates
SAGE_EN = [
    "I will put the remote on the TV stand. Is that right?",
    "I am not sure I understood (the sofa you mentioned is not in my plan). I will put the remote on the TV stand. "
    "Is that right?",
    "Where are you? Which place should I bring it to?",
    "Where are you? Which place should I bring it to? Which grandpa do you mean: bed in the master or sofa in the "
    "living?",
    "Where should the remote go in the end: TV stand in the living or sofa in the living? It cannot be in two places.",
    "Which place do you mean: shelf in the kitchen or tv_stand in the living?",
    "Which shelf do you mean: shelf in the kitchen or shelf in the living?",
    "Which drawer should I open?", "What should I say?", "Where should I go?", "Where should I take it?",
    "Where should I put the remote?", "Where should I put the ? What should I do with the towel?",
    "Where should I put the ? Where should I put the lunch is ready?",
    "You mentioned the sofa. What should I do there?", "What should I do with the remote?",
    "What should I do with the towel?", "What should I do exactly?", "Sorry. What should I do?",
    "Sorry, I did not understand. Could you say the task in other words?", "What should I open?",
    "What should I close?", "Could you say that again?", "Sorry, I may have misheard you. Could you say that again?",
    "Sorry, I didn't catch that. Please answer yes or no.", "I couldn't find the remote. Where is it?",
    "The remote is too far for my arm. Could you move it closer to the edge, then say yes?",
    "I can't pick up the remote. Could you move it closer to the edge, then say yes?",
    "I can't get to the sink in the kitchen. Is something in the way? Please clear the way and say yes.",
    "Sorry, I didn't hear you. Where should I put the remote?",
]


@pytest.mark.parametrize("q", SAGE_EN)
def test_sage_english_templates_read_as_their_meaning(q):
    """In an English episode the user hears SAGE's template itself: the rules read it as the adapter's meaning,
    so the heard-text check never rejects a faithful question (no classifier: rules only)."""
    from homeloop_robot.configs.ra_dialog import derive
    m = derive(q)
    assert m is not None
    _r, log = _ask("en", q, m)
    assert log["path"] == "structured" and log["qtype"] == m["qtype"], (q, m, log)
