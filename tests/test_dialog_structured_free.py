"""How the simulated user reads free text and checks a planner's meaning against what it heard (R2-7a sim-user
audit, docs/user_model.md "Free text" conventions 1-4 and "Korean: the meaning must match the heard text")."""
import pytest

from homeloop_robot import intent
from homeloop_robot.episode import make_episode

HOUSE = "korean_apt_59"
FETCH_GOAL = {"all": [{"pred": "on", "args": ["remote_1", "tv_stand@living"]},
                      {"pred": "said_to", "args": ["grandpa", "dinner_ready"]}]}
FETCH_REQ = {"en": "Put the remote on the TV stand and tell Grandpa dinner is ready.",
             "ko": "리모컨을 TV대 위에 놓고 할아버지한테 저녁 준비됐다고 말해 주세요."}


def _ask(L, q, meaning=None, classifier=None):
    ep = make_episode(HOUSE, 0, "ideal", 0, lang=L, user_spec={"persona": "adult"}, key="free")
    u = ep.user
    u.hear_instruction(FETCH_REQ[L], L)
    u.set_wants(FETCH_GOAL)
    u.classifier = classifier
    r, _h = u.answer(q, L, tuple(ep.world.people["user"].pos), 1.0, meaning=meaning)
    return r, u.log[-1], ep.world


# ------------------------------------------------------------------------------------ the pieces
@pytest.mark.parametrize("q,out", [
    ("Sorry, I didn't hear you. Where is the remote?", "Where is the remote?"),
    ("Sorry, I may have misheard you. Where is the remote?", "Where is the remote?"),
    ("죄송해요, 잘 안 들렸어요. 리모컨 어디 있어요?", "리모컨 어디 있어요?"),
    ("Sorry, I didn't hear you.", "Sorry, I didn't hear you."),          # nothing after it: kept
    ("Sorry, I didn't catch that. Please answer yes or no.", "Sorry, I didn't catch that. Please answer yes or no."),
])
def test_strip_preamble(q, out):
    assert intent.strip_preamble(q) == out


@pytest.mark.parametrize("q,L,out", [
    ("Where is the red book, and where should I bring it to?", "en", "Where is the red book?"),
    ("I will put the mug on the counter. Is that right?", "en", "I will put the mug on the counter. Is that right?"),
    ("You mentioned the dresser. What should I do there? Where should I put it?", "en", "What should I do there?"),
    ("전화는 지금 어디에 있고, 붉은 머그잔은 어디에 놓고 싶으세요?", "ko", "전화는 지금 어디에 있고?"),
    # a Korean list of steps ("A하고, B하고, ... 맞나요?") is one question
    ("제가 침대로 가고, 부엌 냉장고로 가는 거 맞나요?", "ko", "제가 침대로 가고, 부엌 냉장고로 가는 거 맞나요?"),
])
def test_first_question(q, L, out):
    assert intent.first_question(q, L) == out


# ------------------------------------------------------------------------------------ conventions, answered
@pytest.mark.parametrize("L,q", [("en", "Sorry, I didn't hear you. Where is the remote?"),
                                 ("ko", "죄송해요, 잘 안 들렸어요. 리모컨 어디 있어요?")])
def test_reask_preamble_is_not_a_repeat_request(L, q):
    r, log, _ = _ask(L, q)
    assert log["qtype"] == "where_is" and log["why"] == "location" and r.text != FETCH_REQ[L]


@pytest.mark.parametrize("L,q", [("en", "Where is the remote, and where should I bring it to?"),
                                 ("ko", "리모컨은 지금 어디에 있고, 어디에 가져다 놓을까요?")])
def test_compound_question_is_answered_from_the_first(L, q):
    r, log, _ = _ask(L, q)
    assert log["qtype"] == "where_is" and log["why"] == "location"


@pytest.mark.parametrize("L,q", [("en", "What should I do exactly?"), ("en", "What do you want the robot to do?"),
                                 ("en", "You mentioned the sofa. What should I do there?"),
                                 ("en", "Which objects should I move and where should I put them?"),
                                 ("ko", "로봇이 어떤 일을 해야 할까요?"), ("ko", "소파 얘기하셨죠? 거기서 제가 어떻게 해야 할까요?"),
                                 ("ko", "어떤 물건을 원하시고, 어디에 놓고 싶으신지 알려주세요.")])
def test_open_what_to_do_gets_the_task_again(L, q):
    r, log, _ = _ask(L, q)
    assert log["qtype"] == "repeat" and r.text == FETCH_REQ[L]


@pytest.mark.parametrize("L,q,word", [("en", "What do you mean by 'sec'?", "sec"),
                                      ("ko", "'여쇠'가 무슨 뜻이에요?", "여쇠")])
def test_quoted_word_is_a_heard_word_check(L, q, word):
    assert intent.read_free(q, L, _ask(L, "?")[2])[0] == {"qtype": "did_you_mean", "word": word}
    _r, log, _ = _ask(L, q)
    assert log["qtype"] == "did_you_mean"


@pytest.mark.parametrize("L,q", [("ko", "할아버지, 수건을 드립니다."), ("en", "Can you bring me the remote?")])
def test_remark_or_task_for_the_user_asks_nothing(L, q):
    r, log, _ = _ask(L, q)
    assert log["qtype"] == "free" and r.kind == "not_sure"


@pytest.mark.parametrize("L,q", [("en", "What should I tell grandpa?"), ("ko", "할아버지께 뭐라고 말씀드릴까요?")])
def test_what_to_say(L, q):
    r, log, _ = _ask(L, q)
    assert log["qtype"] == "what_to_say" and log["why"] == "goal_message"


@pytest.mark.parametrize("L,q", [("ko", "저한테 리모컨 가져다드릴까요?"), ("en", "Should I put the remote on the TV stand?")])
def test_one_proposal_is_a_yes_no_check(L, q):
    _r, log, _ = _ask(L, q)
    assert log["qtype"] == "confirm"


def test_two_proposals_are_a_choice_not_a_check():
    _r, log, _ = _ask("ko", "리모컨 드릴까요, 휴대폰 드릴까요?")
    assert log["qtype"] != "confirm"


# ------------------------------------------------------------------------------------ meanings about nothing
def test_do_with_an_asr_fragment_gets_the_task_again():
    """SAGE's "What should I do with the X?" about a fragment that names nothing in the house ("chicken bring"):
    the person cannot answer about it and says the task again."""
    m = {"qtype": "which_place", "obj": "chicken bring"}
    r, log, _ = _ask("en", "What should I do with the chicken bring?", m)
    assert log["path"] == "structured" and log["qtype"] == "repeat" and r.text == FETCH_REQ["en"]
    # a real thing keeps its meaning
    _r, log, _ = _ask("en", "What should I do with the remote?", {"qtype": "which_place", "obj": "remote"})
    assert log["qtype"] == "which_place" and log["why"] == "goal_destination"


def test_where_put_with_an_empty_object_still_asks_where():
    w = _ask("en", "?")[2]
    assert intent.ungrounded({"qtype": "which_place", "obj": "?"}, w, "Where should I put the ?") == \
        {"qtype": "which_place"}


# ------------------------------------------------------------------------------------ Korean: heard text decides
def test_korean_meaning_must_match_the_heard_text():
    """The adapter derives "where_are_you" from SAGE's English "Where are you? Which place should I bring it to?",
    but the Korean the user hears is "여기 있어요? 어디에 가져다줘야 할까요?" (a mistranslation: "is it here?"). The
    user answers what it heard, and the mismatch is recorded."""
    q = "여기 있어요? 어디에 가져다줘야 할까요?"
    r, log, _ = _ask("ko", q, {"qtype": "where_are_you"})
    assert log["path"] == "structured_mismatch" and log["qtype"] != "where_are_you"
    # the same meaning with a faithful translation counts
    r, log, _ = _ask("ko", "지금 어디 계세요?", {"qtype": "where_are_you"})
    assert log["path"] == "structured" and log["why"] == "self_position"
    # English episodes hear the template itself: no check
    r, log, _ = _ask("en", "Where are you? Which place should I bring it to?", {"qtype": "where_are_you"})
    assert log["path"] == "structured"


def test_korean_mismatch_without_any_reading_is_not_understood():
    r, log, _ = _ask("ko", "마이크로웨이브@주방 안에 들어가서?", {"qtype": "where_are_you"})
    assert log["path"] == "structured_mismatch" and r.kind == "not_sure"


def test_paths_listed():
    assert intent.PATHS == ("structured", "structured_mismatch", "rules", "llm")
