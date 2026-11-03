"""Fresh pilot round 1 (homeloop_bench docs/experiments.md "Pilot rounds", results/pilot_r27x/round1), tasks
hl-dev-000057 / 000016 / 000060:
- a quoted message names no place ("say 'It's time for bed.'" is not a bed), and a wrong message is corrected by its
  content, not by the person;
- a Korean read-back of the bedtime message ('잠자기 시간', the catalog keywords: tests/test_messages.py) is confirmed;
- "where are X and Y?" is answered for both, and "which desk?" with the desk the object is on;
- a compound read-back of two deliveries: one object's source is not "another place" for the other's person;
- a quote of misheard words ("'언경'은 무슨 뜻이에요?") gets the request again; "which things and where?" gets both."""
import pytest

from homeloop_robot.episode import make_episode

BOOK_GOAL = {"all": [{"pred": "on", "args": ["book_2", "coffee_table@living"]},
                     {"pred": "said_to", "args": ["child", "bedtime"]}]}
BOOK_REQ = {"en": "Can you put the green book on the desk, no, actually on the coffee table? And after that, let my son "
                  "know it's time for bed.",
            "ko": "초록색 책을 책상에, 아 아니다, 거실 탁자에 갖다 놓은 다음에 아들한테 가서 이제 잘 시간이라고 말해 줄 수 있어요?"}
GLASSES_GOAL = {"all": [{"pred": "on", "args": ["glasses_1", "coffee_table@living"]},
                        {"pred": "on", "args": ["remote_1", "coffee_table@living"]}]}
GLASSES_REQ = {"en": "The neighbors are comin' by. Could you put the reading glasses and the remote on the coffee table?",
               "ko": "이웃분이 잠깐 들리신다고 하네요. 안경과 티비 리모컨을 거실 탁자 위에 놓아주실 수 있을까요?"}
GRANDPA_GOAL = {"all": [{"pred": "delivered", "args": ["glasses_1", "user"], "mode": "reach", "mode_reason": None},
                        {"pred": "delivered", "args": ["remote_1", "grandpa"], "mode": "hand",
                         "mode_reason": "user_needs"}]}
GRANDPA_REQ = {"en": "Hey, bring me the glasses and then hand the remote to Grandpa.",
               "ko": "안경 좀 가져와 주실래요? 그리고 아버님께 리모컨 갖다 드릴 수 있을까요?"}


def _user(house, L, goal, req, at=None):
    ep = make_episode(house, 0, "ideal", 0, lang=L, user_spec={"persona": "adult"}, key="fresh-r1")
    for o, p in (at or {}).items():
        ep.world.objects[o].at = p
    u = ep.user
    u.hear_instruction(req[L], L)
    u.set_wants(goal)
    return ep, u


def _ask(house, L, q, goal, req, meaning=None, at=None):
    ep, u = _user(house, L, goal, req, at)
    r, _h = u.answer(q, L, tuple(ep.world.people[ep.world.user_id()].pos), 1.0, meaning=meaning)
    return r, u.log[-1]


# ---- 057: a quoted message, a wrong message, the bedtime keywords ------------------------------------------------

EN_057 = ('I will put the green book from the kids_desk in the kids on the coffee_table in the living, then say '
          '"It\'s time for bed, kid." in the kid. Is that right?')


def test_quoted_message_names_no_place():
    for meaning in (None, {"qtype": "confirm", "goal": EN_057[:-len(" Is that right?")]}):
        r, log = _ask("family_house", "en", EN_057, BOOK_GOAL, BOOK_REQ, meaning, at={"book_2": "kids_desk@kids"})
        assert r.kind == "yes", (r.text, log)


def test_korean_bedtime_read_back_is_confirmed():
    q = '아이들 책상에 있는 녹색 책을 거실의 커피 테이블에 두고, 아이한테 "잠자기 시간이에요"라고 말할 거예요. 맞죠?'
    r, log = _ask("family_house", "ko", q, BOOK_GOAL, BOOK_REQ, at={"book_2": "kids_desk@kids"})
    assert r.kind == "yes", (r.text, log)


@pytest.mark.parametrize("L,q,want", [
    ("en", 'I will put the green book on the coffee table, then say "Dinner is ready." to the kid. Is that right?',
     "No, tell the kid: It is time for bed."),
    ("ko", '녹색 책을 커피 테이블에 두고, 아이한테 "저녁 준비됐어요"라고 말할 거예요. 맞죠?',
     '아니요, 아이한테 "이제 잘 시간이에요"라고 말해 주세요.'),
])
def test_wrong_message_is_corrected_by_its_content(L, q, want):
    r, _log = _ask("family_house", L, q, BOOK_GOAL, BOOK_REQ)
    assert r.kind == "no" and r.text == want, r.text


def test_wrong_person_is_still_corrected_by_the_person():
    q = 'I will put the green book on the coffee table, then say "It is time for bed." to grandma. Is that right?'
    r, _log = _ask("family_house", "en", q, BOOK_GOAL, BOOK_REQ)
    assert r.kind == "no" and "kid" in r.text and "bed" not in r.text, r.text


# ---- 016: where are both, which desk -------------------------------------------------------------------------

AT_016 = {"glasses_1": "desk@study", "remote_1": "sofa@living"}


@pytest.mark.parametrize("meaning", [None, {"qtype": "where_is", "obj": "reading glasses and the remote"}])
def test_where_are_two_objects(meaning):
    r, log = _ask("family_house", "en", "Where are the reading glasses and the remote now?", GLASSES_GOAL,
                  GLASSES_REQ, meaning, at=AT_016)
    assert r.kind == "correct", (r.text, log)
    assert "desk in the study" in r.text and "sofa" in r.text, r.text
    r, _log = _ask("family_house", "ko", "안경과 리모컨은 지금 어디에 있어요?", GLASSES_GOAL, GLASSES_REQ, at=AT_016)
    assert "서재 책상" in r.text and "소파" in r.text, r.text


def test_one_object_still_one_place():
    r, _log = _ask("family_house", "en", "Where are the reading glasses?", GLASSES_GOAL, GLASSES_REQ, at=AT_016)
    assert r.text == "It's on the desk in the study.", r.text


@pytest.mark.parametrize("L,q", [("en", "Which desk do you mean?"), ("en", "Which desk and which coffee table do you mean?"),
                                 ("ko", "어느 책상이요?")])
def test_which_desk(L, q):
    r, log = _ask("family_house", L, q, GLASSES_GOAL, GLASSES_REQ, at=AT_016)
    assert r.kind == "correct" and ("desk in the study" in r.text or "서재 책상" in r.text), (r.text, log)


# ---- 060: a compound read-back, misheard words, which things and where -----------------------------------------

AT_060 = {"glasses_1": "tv_stand@living", "remote_1": "coffee_table@living"}


def test_compound_read_back_other_objects_source_is_not_another_place():
    en = ("I will put the black glasses from the tv_stand in the living on the spot within your reach, then put the "
          "black remote from the coffee_table in the living on the grandpa.")
    for meaning in (None, {"qtype": "confirm", "goal": en}):
        r, log = _ask("korean_apt_59", "en", en + " Is that right?", GRANDPA_GOAL, GRANDPA_REQ, meaning, at=AT_060)
        assert r.kind == "yes", (r.text, log)
    # a place that is no object's source and not grandpa's is still another place
    bad = en.replace("on the grandpa", "on the grandpa on the shoe cabinet")
    r, _log = _ask("korean_apt_59", "en", bad + " Is that right?", GRANDPA_GOAL, GRANDPA_REQ, at=AT_060)
    assert r.kind == "no", r.text


def test_misheard_words_get_the_request_again():
    q = "'언경'과 '리컨 갖단 드'는 무슨 뜻이에요? 할아버지께 특정 물건을 가져다드리는 건가요?"
    r, log = _ask("korean_apt_59", "ko", q, GRANDPA_GOAL, GRANDPA_REQ, at=AT_060)
    assert log["why"] == "repeat_request" and r.text.startswith("안경"), (r.text, log)
    # a word of the request itself is still confirmed (B3)
    r, log = _ask("korean_apt_59", "en", "Did you mean 'glasses'?", GRANDPA_GOAL, GRANDPA_REQ, at=AT_060)
    assert r.kind == "yes", (r.text, log)


def test_which_things_and_where_gets_both():
    q = "어떤 물건을 가져다드릴지, 그리고 어디에 놓아드릴지 구체적으로 알려주실 수 있나요?"
    r, log = _ask("korean_apt_59", "ko", q, GRANDPA_GOAL, GRANDPA_REQ, at=AT_060)
    assert "안경" in r.text and "리모컨" in r.text and "할아버지" in r.text and "저한테" in r.text, (r.text, log)
    # a which-object question alone is answered as before
    r, _log = _ask("korean_apt_59", "ko", "어떤 물건을 가져다드릴까요?", GRANDPA_GOAL, GRANDPA_REQ, at=AT_060)
    assert "할아버지" not in r.text, r.text
