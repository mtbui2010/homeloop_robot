"""30-task gate, round 1 (homeloop_bench docs/experiments.md "Pilot rounds", results/gate30_r27/round1): the simulated
user answers read-backs and questions as the person who asked would. Worlds: the gate tasks' houses and start
states (house, seed_state, persona), goals as in the tasks.

- S1 (011 / 005 / 018 / 024): a delivery put down ON the person's own seat or bed is not "to me" (the judge fails it);
  a support surface the person can reach is, when they asked for the thing to be brought (mode reach);
- S2 (018): the person's seat said only as a waypoint, or the object's part bringing it to another person, does not
  confirm a delivery to the speaker;
- S3 (024): the places of the other parts of a compound read-back (", then go to the dock") are not where a message
  is said;
- S4 (006 / 005 / 014 / 021): "on the fridge" for "in the fridge" is corrected;
- S6 (000): a read-back of a request that only opens the microwave must say "open"; "where should I put the
  microwave?" gets "just open it";
- S7 (024 / 015): "A first, or B?" is a choice of order, answered with the request; options inside the room a message
  names get the message; a second "Where are you?" in the same turn is answered too."""
import pytest

from homeloop_robot.episode import make_episode


def _user(house, seed_state, persona, L, goal, request):
    ep = make_episode(house, seed_state, "ideal", 0, lang=L, user_spec={"persona": persona}, key="gate30-r1")
    u = ep.user
    u.hear_instruction(request, L)
    u.set_wants(goal)
    return ep, u


def _ask(ep, u, q, L, meaning=None):
    r, _h = u.answer(q, L, tuple(ep.world.person_xy(u.user_id)), 1.0, meaning=meaning)
    return r, u.log[-1]


# ── S1: hl-dev-000011, grandma on the armchair, side table beside her ──────────────────────────────────────────────
G011 = {"all": [{"pred": "delivered", "args": ["mug_1", "grandma"], "mode": "reach", "mode_reason": None},
                {"pred": "delivered", "args": ["water_bottle_1", "grandma"], "mode": "reach", "mode_reason": None}]}
R011 = {"en": "My back is really bad today, so I'd rather not get up. Could you grab the red mug for me and grab the "
              "water bottle for me?",
        "ko": "오늘 허리가 너무 아파서 일어나기가 힘들어요. 빨간 머그컵을 갖다주고 물병을 갖다줘요."}
STORED_011 = ("I will put the red mug from the counter in the kitchen on the armchair in the living, then put the water "
              "bottle from the counter in the kitchen on the armchair in the living. Is that right?")


@pytest.mark.parametrize("L,q", [
    ("en", STORED_011),
    ("en", "I will put the red mug on the armchair, then put the water bottle on the armchair. Is that right?"),
    ("ko", "빨간 머그컵과 물병을 거실 안락의자에 둘게요. 맞죠?"),
    ("ko", "빨간 머그컵을 안락의자 위에 놓고, 물병도 안락의자 위에 놓을게요. 맞죠?"),
])
def test_011_put_on_her_own_seat_is_corrected(L, q):
    ep, u = _user("senior_flat", 1414, "older", L, G011, R011[L])
    r, log = _ask(ep, u, q, L, {"qtype": "confirm", "goal": q} if L == "en" else None)
    assert r.kind == "no" and ("red mug" in r.text or "머그컵" in r.text), (r.text, log)


@pytest.mark.parametrize("L,q", [
    ("en", "I will put the red mug from the counter in the kitchen on the side table in the living, then put the water "
           "bottle from the counter in the kitchen on the side table in the living. Is that right?"),
    ("en", "I will bring the red mug and the water bottle to the armchair in the living. Is that right?"),
    ("en", "I will put the red mug on the spot within your reach, then put the water bottle on the spot within your "
           "reach. Is that right?"),
    ("ko", "빨간 머그컵과 물병을 거실 사이드 테이블에 둘게요. 맞죠?"),
])
def test_011_a_surface_she_can_reach_or_bringing_it_to_her_seat_is_confirmed(L, q):
    ep, u = _user("senior_flat", 1414, "older", L, G011, R011[L])
    r, log = _ask(ep, u, q, L)
    assert r.kind == "yes", (r.text, log)


def test_011_a_surface_out_of_her_reach_is_not_confirmed():
    ep, u = _user("senior_flat", 1414, "older", "en", G011, R011["en"])
    r, log = _ask(ep, u, "I will put the red mug and the water bottle on the coffee table in the living. Is that right?",
                  "en")
    assert r.kind == "no", (r.text, log)


def test_005_hand_delivery_put_on_a_surface_or_her_chair_is_corrected():
    goal = {"all": [{"pred": "in", "args": ["apple_1", "fridge@kitchen"]},
                    {"pred": "delivered", "args": ["mug_1", "user"], "mode": "hand", "mode_reason": "explicit"}]}
    req = ("Could you put the apple in the fridge, and while you're in the kitchen, bring me the white mug? I'd like "
           "the white mug right in my hand.")
    ep, u = _user("korean_apt_59", 5524, "adult", "en", goal, req)
    stored = ("I am not sure I understood (the chicken bring is not in my plan; the hard is not in my plan). I will put "
              "the apple from the spot within your reach in the fridge in the kitchen, then put the white mug from the "
              "spot within your reach on the desk_chair in the small. Is that right?")
    r, log = _ask(ep, u, stored, "en")
    assert r.kind == "no" and "mug" in r.text, (r.text, log)
    # the desk next to her is a support surface she reaches, but she asked for the mug in her hand
    r, log = _ask(ep, u, "I will put the apple in the fridge, then put the white mug on the desk in the small. "
                         "Is that right?", "en")
    assert r.kind == "no" and "mug" in r.text, (r.text, log)


# ── S2: hl-dev-000018, the speaker at the desk chair in the small room, the phone for grandpa ─────────────────────
G018 = {"all": [{"pred": "delivered", "args": ["book_2", "user"], "mode": "reach", "mode_reason": None},
                {"pred": "delivered", "args": ["phone_1", "grandpa"], "mode": "hand", "mode_reason": "user_needs"},
                {"pred": "docked", "args": []}]}
R018 = ("Fetch the green book for me and bring Grandpa the cell phone, please. After that, you can go back and "
        "charge.")


@pytest.mark.parametrize("q", [
    # the stored k4 (sage EN): her seat only as a waypoint, the book "on the grandpa"
    "I will go to the bookshelf in the small, then put the grin book on the grandpa, then go to the desk_chair in the "
    "small, then put the blue phone from the desk_chair in the small on the grandpa, then go to the dock in the "
    "living. Is that right?",
    # the stored k3 (sage_norag EN): the book on her seat
    "I will put the grin book on the desk_chair in the small, then put the cell phone from the desk in the small on "
    "the grandpa, then go to the dock in the living. Is that right?",
])
def test_018_the_book_is_corrected_first(q):
    ep, u = _user("korean_apt_59", 1700, "adult", "en", G018, R018)
    r, log = _ask(ep, u, q, "en", {"qtype": "confirm", "goal": q})
    assert r.kind == "no" and "green book" in r.text, (r.text, log)


def test_018_a_right_read_back_is_still_confirmed():
    ep, u = _user("korean_apt_59", 1700, "adult", "en", G018, R018)
    q = ("I will go to the bookshelf in the small, then put the green book on the spot within your reach, then go to "
         "the desk in the small, then put the phone from the desk in the small on the grandpa, then go to the dock "
         "in the living. Is that right?")
    r, log = _ask(ep, u, q, "en")
    assert r.kind == "yes", (r.text, log)


# ── S3 / S7a: hl-dev-000024, mom in bed, a message to the kid, the dock at the end ──────────────────────────────────
G024 = {"all": [{"pred": "said_to", "args": ["child", "wake_up"]},
                {"pred": "delivered", "args": ["vitamins_1", "mom"], "mode": "hand", "mode_reason": "no_surface"},
                {"pred": "docked", "args": []}]}
R024 = "Wake my son up, and then grab the vitamins for me. After that, you can go back and charge."


def test_024_the_dock_and_the_other_parts_are_not_where_the_message_is_said():
    ep, u = _user("family_house", 4436, "child_present", "en", G024, R024)
    right = ('I will say "Wake up, kid!" to the kid, then go to the dining_table in the kitchen, then bring the '
             'vitamins to you, then go to the dock in the living. Is that right?')
    r, log = _ask(ep, u, right, "en")
    assert r.kind == "yes", (r.text, log)
    # the stored k3: the message is right now, the vitamins "on the kid" are what is wrong
    k3 = ('I will say "Wake up, kid!" in the kid, then go to the fridge in the kitchen, then put the vitamins from the '
          'dining_table in the kitchen on the kid, then go to the dock in the living. Is that right?')
    r, log = _ask(ep, u, k3, "en")
    assert r.kind == "no" and "vitamin" in r.text, (r.text, log)
    # a message said in another room is still not one for the kid
    r, log = _ask(ep, u, 'I will go to the sofa in the living and say "Wake up, kid!", then bring the vitamins to you, '
                         'then go to the dock in the living. Is that right?', "en")
    assert r.kind == "no" and "kid" in r.text, (r.text, log)


def test_024_the_vitamins_on_her_bed_are_corrected():
    ep, u = _user("family_house", 4436, "child_present", "en", G024, R024)
    q = ('I will say "Wake up, kid!" to the kid, then put the vitamins from the dining_table in the kitchen on the bed '
         'in the master, then go to the dock in the living. Is that right?')
    r, log = _ask(ep, u, q, "en")
    assert r.kind == "no" and "vitamin" in r.text, (r.text, log)


def test_024_which_first_is_answered_with_the_request():
    ep, u = _user("family_house", 4436, "child_present", "en", G024, R024)
    r, log = _ask(ep, u, "Should I wake the kid first, or should I go to the fridge to grab the vitamins?", "en")
    assert r.kind == "correct" and r.text == R024 and log["why"] == "goal_order", (r.text, log)
    # a plain yes / no proposal is still one
    r, log = _ask(ep, u, "Should I wake the kid first?", "en")
    assert r.kind in ("yes", "no"), (r.text, log)


# ── S4: hl-dev-000006, the apple into the fridge ─────────────────────────────────────────────────────────────────
G006 = {"all": [{"pred": "in", "args": ["apple_1", "fridge@kitchen"]},
                {"pred": "delivered", "args": ["towel_1", "user"], "mode": "reach", "mode_reason": None},
                {"pred": "docked", "args": []}]}
R006 = {"en": "Hey, first put the apple in the fridge, then grab me the towel. After that, you're good to go back "
              "and charge.",
        "ko": "사과 좀 냉장고에 넣어 주실 수 있을까요? 그리고 수건 가져다주실 수 있으신가요? 그 다음에 충전해 주시려면 되나요?"}


@pytest.mark.parametrize("L,q,ok", [
    ("en", "I will put the apple from the dining_table in the kitchen on the fridge in the kitchen, then put the towel "
           "on the spot within your reach, then go to the dock in the living. Is that right?", False),
    ("en", "I will put the apple in the fridge in the kitchen, then put the towel on the spot within your reach, then "
           "go to the dock in the living. Is that right?", True),
    ("ko", "사과를 냉장고 위에 올려 두고, 수건은 손이 닿는 곳에 둔 다음 충전하러 갈게요. 맞죠?", False),
    ("ko", "사과를 냉장고에 넣고, 수건은 손이 닿는 곳에 둔 다음 충전하러 갈게요. 맞죠?", True),
])
def test_006_on_the_fridge_is_not_in_the_fridge(L, q, ok):
    ep, u = _user("korean_apt_59", 7624, "adult", L, G006, R006[L])
    r, log = _ask(ep, u, q, L)
    if ok:
        assert r.kind == "yes", (r.text, log)
    else:
        assert r.kind == "no" and ("fridge" in r.text or "냉장고" in r.text), (r.text, log)


# ── S6: hl-dev-000000, open the microwave ─────────────────────────────────────────────────────────────────────────
G000 = {"all": [{"pred": "open", "args": ["microwave@kitchen"]}]}
R000 = {"en": "I'd like to take a look inside the microwave. Could you open the door?",
        "ko": "전자레인지 안 좀 살펴봤으면 좋겠어요. 문 좀 열어 주시겠어요?"}


@pytest.mark.parametrize("L,q,meaning,ok", [
    ("ko", "요리용 마이크로웨이브를 주방에 두겠습니다. 맞죠?",
     {"qtype": "confirm", "goal": "I will put the microwave@kitchen on the microwave in the kitchen."}, False),
    ("ko", "전자레인지를 바닥에 내려놓겠습니다. 맞죠?", None, False),
    ("en", "I will put the microwave on the microwave in the kitchen. Is that right?", None, False),
    ("ko", "주방 전자레인지를 열겠습니다. 맞죠?", None, True),
    ("en", "I will open the microwave in the kitchen. Is that right?", None, True),
])
def test_000_opening_must_be_said(L, q, meaning, ok):
    ep, u = _user("shared_flat", 3693, "adult", L, G000, R000[L])
    r, log = _ask(ep, u, q, L, meaning)
    if ok:
        assert r.kind == "yes", (r.text, log)
    else:
        assert r.kind == "no" and ("open" in r.text or "열어" in r.text), (r.text, log)


@pytest.mark.parametrize("L,q,meaning", [
    ("ko", "죄송해요, 제가 잘못 듣지 않았나요? 마이크로웨이브를 어디에 두면 될까요?",
     {"qtype": "which_place", "obj": "microwave@kitchen", "template": ["where_put"]}),
    ("en", "Where should I put the microwave?", None),
])
def test_000_where_to_put_the_microwave_gets_just_open_it(L, q, meaning):
    ep, u = _user("shared_flat", 3693, "adult", L, G000, R000[L])
    r, log = _ask(ep, u, q, L, meaning)
    assert log["why"] == "goal_open" and ("open" in log["text"] or "열어" in log["text"]), (r.text, log)


def test_000_with_something_to_put_in_naming_the_container_is_enough():
    goal = {"all": [{"pred": "open", "args": ["fridge@kitchen"]}, {"pred": "in", "args": ["mug_1", "fridge@kitchen"]}]}
    ep, u = _user("shared_flat", 3693, "adult", "en", goal, "Open the fridge and put the mug inside, and leave it open.")
    r, log = _ask(ep, u, "I will put the mug in the fridge in the kitchen. Is that right?", "en")
    assert r.kind == "yes", (r.text, log)


# ── S7b: hl-dev-000015, "tell Grandpa to head to the kitchen" ─────────────────────────────────────────────────────
G015 = {"all": [{"pred": "said_to", "args": ["grandpa", "come_kitchen"]},
                {"pred": "delivered", "args": ["book_1", "user"], "mode": "reach", "mode_reason": None}]}
R015 = "Hey, tell Grandpa to head to the kitchen for a sec and bring that red book over to me."
OPTS = ["counter in the kitchen", "dining_table in the kitchen", "drawer in the kitchen", "floor in the kitchen",
        "fridge in the kitchen", "kimchi_fridge in the kitchen", "kitchen_sink in the kitchen", "microwave in the kitchen",
        "stove in the kitchen"]
Q015 = "Which place do you mean: " + " or ".join(OPTS) + "?"


def test_015_places_in_the_room_of_the_message_get_the_message():
    ep, u = _user("korean_apt_59", 9184, "adult", "en", G015, R015)
    r, log = _ask(ep, u, Q015, "en", {"qtype": "which_place", "options": OPTS, "template": ["which_place"]})
    assert log["why"] == "goal_place_message" and "Please come to the kitchen." in log["text"], (r.text, log)
    assert "I'm at" not in log["text"]


def test_015_a_second_where_are_you_is_answered_too():
    ep, u = _user("korean_apt_59", 9184, "adult", "en", G015, R015)
    q = "Sorry, I didn't hear you. " + Q015 + " Where are you? Which place should I bring it to?"
    r, log = _ask(ep, u, q, "en", {"qtype": "which_place", "options": OPTS,
                                   "template": ["silence_retry", "which_place", "where_user"]})
    assert "Please come to the kitchen." in log["text"] and log["text"].endswith("I'm at the sofa."), (r.text, log)
