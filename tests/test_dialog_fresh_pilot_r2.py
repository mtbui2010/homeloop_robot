"""Fresh pilot round 2 (homeloop_bench docs/experiments.md "Pilot rounds", results/pilot_r27x/round2), tasks
hl-dev-000060 / 000057:
- a place said as where an object comes from ("the remote from the coffee table", '커피 테이블에 있는 리모컨'), even a
  wrong one, or where the robot goes on the way ("go to the desk chair, then ...") is not a place the object is
  brought to: the delivery to grandpa is covered, and the correction names what is really wrong;
- a Korean place name with the plural marker 들 ('아이들 책상' for '아이 책상') names that place, not the study desk, so
  a right Korean read-back agrees with its English meaning (no structured_mismatch)."""
import pytest

from homeloop_robot import dialog as D
from homeloop_robot import intent
from homeloop_robot.episode import make_episode

GRANDPA_GOAL = {"all": [{"pred": "delivered", "args": ["glasses_1", "user"], "mode": "reach", "mode_reason": None},
                        {"pred": "delivered", "args": ["remote_1", "grandpa"], "mode": "hand",
                         "mode_reason": "user_needs"}]}
GRANDPA_REQ = {"en": "Hey, bring me the glasses and then hand the remote to Grandpa.",
               "ko": "안경 좀 가져와 주실래요? 그리고 아버님께 리모컨 갖다 드릴 수 있을까요?"}
# the round 2 episode: the remote is on the sofa, the speaker sits on the desk chair of the small room
AT_060 = {"glasses_1": "tv_stand@living", "remote_1": "sofa@living"}
BOOK_GOAL = {"all": [{"pred": "on", "args": ["book_2", "coffee_table@living"]},
                     {"pred": "said_to", "args": ["child", "bedtime"]}]}
BOOK_REQ = {"ko": "초록색 책을 책상에, 아 아니다, 거실 탁자에 갖다 놓은 다음에 아들한테 가서 이제 잘 시간이라고 말해 줄 수 있어요?"}


def _ask(house, L, q, goal, req, meaning=None, at=None, seat=None):
    ep = make_episode(house, 0, "ideal", 0, lang=L, user_spec={"persona": "adult"}, key="fresh-r2")
    for o, p in (at or {}).items():
        ep.world.objects[o].at = p
        ep.world.initial_at[o] = p          # where the episode placed it at the start
    if seat:
        ep.world.people[ep.world.user_id()].seat = seat
    u = ep.user
    u.hear_instruction(req[L], L)
    u.set_wants(goal)
    r, _h = u.answer(q, L, tuple(ep.world.people[ep.world.user_id()].pos), 1.0, meaning=meaning)
    return r, u.log[-1]


# ---- 060: a source or a waypoint is not where the object goes -------------------------------------------------

# sage KO, round 2, Q4: the English meaning and the Korean the user heard (a wrong source for the remote, the
# speaker's seat in a go-to clause; the destinations are right)
SAGE_EN = ("I will go to the desk_chair in the small, then put the glasses from the desk_chair in the small on the spot "
           "within your reach, then put the remote from the spot within your reach on the grandpa.")
SAGE_KO = ("작은 곳에 있는 책상의 의자에 가서, 그 의자 위에 있는 안경을 당신이 닿을 수 있는 곳에 두고, 그 곳에 있는 리모컨을 "
           "할아버지에게 두겠습니다. 맞죠?")
# sage_norag KO, round 2, Q4 / Q5: the remote's source is wrong, and the heard Korean puts the glasses in the living
# room instead of bringing them to the speaker
NORAG_EN = ("I will put the 안경 from the tv_stand in the living on the spot within your reach, then put the 리모컨 from "
            "the coffee_table in the living on the grandpa.")
NORAG_KO = "TV 스탠드에 있는 안경은 거실에 바로 놓고, 커피 테이블에 있는 리모컨은 할아버지께 놓겠습니다. 맞죠?"


@pytest.mark.parametrize("goal", [SAGE_EN, NORAG_EN])
def test_wrong_source_and_go_to_clause_are_not_another_place(goal):
    r, log = _ask("korean_apt_59", "en", goal + " Is that right?", GRANDPA_GOAL, GRANDPA_REQ, at=AT_060,
                  seat="desk_chair@small")
    assert r.kind == "yes", (r.text, log)


def test_sage_ko_read_back_structured_and_heard_agree():
    r, log = _ask("korean_apt_59", "ko", SAGE_KO, GRANDPA_GOAL, GRANDPA_REQ, {"qtype": "confirm", "goal": SAGE_EN},
                  at=AT_060, seat="desk_chair@small")
    assert r.kind == "yes" and log["path"] == "structured", (r.text, log)


def test_norag_ko_correction_names_the_real_problem():
    # the user heard the glasses go to the living room: "no, bring the glasses to me", not the remote again
    for meaning in (None, {"qtype": "confirm", "goal": NORAG_EN}):
        r, log = _ask("korean_apt_59", "ko", NORAG_KO, GRANDPA_GOAL, GRANDPA_REQ, meaning, at=AT_060,
                      seat="desk_chair@small")
        assert r.kind == "no" and "안경" in r.text and "저한테" in r.text and "리모컨" not in r.text, (r.text, log)


@pytest.mark.parametrize("L,q", [
    ("en", "I will put the glasses on the spot within your reach, then put the remote on the shoe cabinet for "
           "grandpa. Is that right?"),
    ("en", "I will put the glasses on the spot within your reach, then go to grandpa and put the remote on the "
           "dining table. Is that right?"),
    ("ko", "안경은 손이 닿는 곳에 두고, 리모컨은 할아버지께 드리려고 신발장에 놓겠습니다. 맞죠?"),
])
def test_a_place_the_object_goes_to_is_still_another_place(L, q):
    r, log = _ask("korean_apt_59", L, q, GRANDPA_GOAL, GRANDPA_REQ, at=AT_060, seat="desk_chair@small")
    assert r.kind == "no" and ("remote" in r.text or "리모컨" in r.text), (r.text, log)


def test_strip_route_places():
    ep = make_episode("korean_apt_59", 0, "ideal", 0, lang="en", user_spec={"persona": "adult"}, key="fresh-r2")
    w = ep.world
    t = D.strip_route_places(w, "put the remote from the coffee table in the living on the shoe cabinet")
    assert "coffee table" not in t and "shoe cabinet" in t
    t = D.strip_route_places(w, "go to the desk chair, then hand it over")
    assert "desk chair" not in t
    t = D.strip_route_places(w, "커피 테이블에 있는 리모컨을 신발장에 놓고 의자에 가서")
    assert "커피 테이블" not in t and "신발장" in t and "의자" not in t


# ---- 057: '아이들 책상' is the kid's desk ---------------------------------------------------------------------

BOOK_EN = ("I will put the green book from the kids_desk in the kids on the coffee_table in the living, then say "
           "\"It's time to sleep\" in the kid.")
BOOK_KO = ['책상 얘기가 제 계획에 없어서 잘 이해한 건지 확신이 안 돼요. 아이들 책상에 있는 녹색 책을 거실의 커피 테이블에 두고, '
           '아이들에게 "잠자기 시간이에요"라고 말할 거예요. 맞죠?',
           '죄송해요, 잘 듣지 못했어요. 책상이 계획에 없어서 이해가 잘 안 돼요. 아이들 책상에서 녹색 책을 거실의 커피 테이블에 '
           '두고, 아이들에게 "잠자기 시간이에요"라고 말할 거예요. 맞죠?']


def test_ko_plural_forms():
    assert D.ko_plural_forms("아이 책상") == ["아이 책상", "아이들 책상"]
    assert D.ko_plural_forms("책상") == ["책상"] and D.ko_plural_forms("TV 스탠드") == ["TV 스탠드"]
    assert D.ko_plural_forms("kid's desk") == ["kid's desk"]


def test_plural_names_the_kids_desk_not_the_study_desk():
    ep = make_episode("family_house", 0, "ideal", 0, lang="ko", user_spec={"persona": "adult"}, key="fresh-r2")
    w = ep.world
    assert intent.entities(w, "아이들 책상에 있는 녹색 책")["place"] == {"kids_desk@kids"}
    assert intent.entities(w, "아이 책상에 있는 녹색 책")["place"] == {"kids_desk@kids"}
    assert intent.entities(w, "책상 위에 있는 녹색 책")["place"] == {"desk@study"}


@pytest.mark.parametrize("q", BOOK_KO)
def test_ko_bedtime_read_back_is_structured(q):
    r, log = _ask("family_house", "ko", q, BOOK_GOAL, BOOK_REQ, {"qtype": "confirm", "goal": BOOK_EN},
                  at={"book_2": "kids_desk@kids"})
    assert r.kind == "yes" and log["path"] == "structured", (r.text, log)


# ---- the route / source rule stays narrow (sim-user audit cases) ------------------------------------------------

WATER_GOAL = {"all": [{"pred": "on", "args": ["book_2", "tv_stand@living"]},
                      {"pred": "delivered", "args": ["water_bottle_1", "grandma"], "mode": "reach",
                       "mode_reason": None}]}
WATER_REQ = {"ko": "파란 책은 거실 TV 스탠드에 두고, 물병은 저한테 갖다 주세요."}


def test_a_place_said_in_the_objects_own_part_is_where_it_goes():
    # audit q0115 (hl-dev-000008 KO): the TV stand is the book's destination, but it is said for the water bottle
    # that goes to the speaker; the go-to clauses before it do not decide it
    q = ("저녁탁자에 있는 파란 책을 거실의 TV 스탠드에 두고, 거실 바닥으로 가서, 주방 선반으로 가서, 주방 카운터에 있는 물병을 "
         "거실 TV 스탠드에 두는 거죠? 맞죠?")
    r, log = _ask("senior_flat", "ko", q, WATER_GOAL, WATER_REQ,
                  at={"book_2": "nightstand@bedroom", "water_bottle_1": "counter@kitchen"})
    assert r.kind == "no" and "물병" in r.text, (r.text, log)


def test_a_message_said_at_another_place_is_still_another_place():
    # audit q0373 (couple_flat KO): '침대에서 ... 말할 거예요' says where the robot speaks; the husband is not there
    goal = {"all": [{"pred": "said_to", "args": ["partner_b", "lunch_ready"]}]}
    req = {"ko": "남편한테 점심 준비됐다고 말해 주세요."}
    q = '침실 침대에서 “남편님, 점심 준비 끝났어요.”라고 말할 거예요. 맞죠?'
    r, log = _ask("couple_flat", "ko", q, goal, req)
    assert r.kind == "no", (r.text, log)
