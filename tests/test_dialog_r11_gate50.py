"""r11 n50 gate (homeloop_bench docs/experiments.md, Round 11): four simulated-user / detector consistency fixes found by
the per-task analysis. Worlds: the gate tasks' houses and start states. No rate or scoring value changed."""
import pytest

from homeloop_robot.episode import make_episode


def _ep(house, seed_state, persona, L, goal, request):
    ep = make_episode(house, seed_state, "ideal", 0, lang=L, user_spec={"persona": persona}, key="r11-gate50")
    ep.user.hear_instruction(request, L)
    ep.user.set_wants(goal)
    return ep


def _ask(ep, q, L):
    r, _h = ep.user.answer(q, L, tuple(ep.world.person_xy(ep.user.user_id)), 1.0)
    return r, ep.user.log[-1]


# ── S2: hl-dev-000030, "check the kitchen table, if the milk is there ..., then tell my husband lunch's ready" ───────
G030 = {"all": [{"pred": "unmoved", "args": ["milk_1"]}, {"pred": "said_to", "args": ["partner_b", "lunch_ready"]}]}
R030 = ("Hey, quick, check the kitchen table. If the milk's there, stick it in the fridge, but if not, just leave it. "
        "Then tell my husband lunch's ready.")


def test_030_the_check_place_of_a_conditional_is_part_of_the_request():
    ep = _ep("couple_flat", 8307, "adult", "en", G030, R030)
    r, log = _ask(ep, 'I will go to the kitchen table, then tell husband: "lunch\'s ready". Is that right?', "en")
    assert r.kind == "yes", (r.text, log)


def test_030_a_place_the_request_does_not_name_is_still_a_wrong_place_for_the_message():
    ep = _ep("couple_flat", 8307, "adult", "en", G030, R030)
    r, log = _ask(ep, 'I will go to the bedroom bed, then tell husband: "lunch\'s ready". Is that right?', "en")
    assert r.kind == "no", (r.text, log)


# ── S3: hl-dev-000042 KO, "A 방 책상 아니면 C 방 책상 중에 어느 쪽을 말씀하시는 거예요?" ────────────────────────────────
G042 = {"all": [{"pred": "in", "args": ["towel_1", "closet@room_a"]}, {"pred": "on", "args": ["snack_1", "desk@room_a"]}]}
R042 = "하얀 수건을 제 방 옷장에 깔끔하게 정리해 주시고, 과자는 제 책상 위로 옮겨 주실래요?"
M042 = {"options": ["desk in the room_a", "desk in the room_c"], "qtype": "which_place", "template": ["which_x"]}


def test_042_desk_is_not_book_with_a_particle():
    from homeloop_robot import dialog as D, intent as I
    ep = _ep("shared_flat", 514, "adult", "ko", G042, R042)
    w = ep.world
    assert {w.objects[o].cls for o in w.objects} >= {"book"}           # the house has books (책)
    q = "A 방 책상 아니면 C 방 책상 중에 어느 쪽을 말씀하시는 거예요?"
    assert not I._thing_word(w, q)                                       # 책상 (a house place) is not 책 + a particle
    assert I._thing_word(w, "책은 어디에 두나요?") and I._thing_word(w, "책을 말씀하시는 거예요?")
    # D.mentions has the same prefix problem for a bare head word of a room-qualified name
    assert not D.mentions("책상", "책", "ko", w) and not D.mentions("A 방 책상", "책", "ko", w)
    assert D.mentions("책을", "책", "ko", w)
    r, log = _ask_m(ep, q, "ko", M042)
    assert r.text == "A 방 책상요." and log["why"] != "not_understood", (r.text, log)


def _ask_m(ep, q, L, meaning):
    r, _h = ep.user.answer(q, L, tuple(ep.world.person_xy(ep.user.user_id)), 1.0, meaning=meaning)
    return r, ep.user.log[-1]


# ── S4: hl-dev-000038 KO, open the drawer, the foil in it, then the dock ─────────────────────────────────────────────
G038 = {"all": [{"pred": "open", "args": ["drawer@kitchen"]}, {"pred": "in", "args": ["foil_1", "drawer@kitchen"]},
                {"pred": "docked", "args": []}]}
R038 = {"ko": "주방 서랍을 열어서 쿠킹포일을 안에 넣어 주시겠어요? 다 마치시면 충전기로 이동해 주세요.",
        "en": "Open the kitchen drawer and stick the aluminum foil inside, then head back to your charger."}
RB038 = {"ko": "요리용 호일 주방 서랍 안에 넣을게요, 그다음 주방 서랍 닫을게요, 그다음 충전기 쪽으로 갈게요. 맞아요?",
         "en": "I will put the foil in the kitchen drawer, then close the kitchen drawer, then go to the living room "
               "charging dock. Is that right?"}


@pytest.mark.parametrize("L", ["ko", "en"])
def test_038_a_readback_that_closes_the_drawer_is_not_the_open_drawer(L):
    ep = _ep("shared_flat", 7189, "adult", L, G038, R038[L])
    r, log = _ask(ep, RB038[L], L)
    assert r.kind == "no", (r.text, log)
    # the correction names the drawer (fix_open), and the same read-back with "open" is still confirmed
    ok = {"ko": "주방 서랍을 열고 요리용 호일 주방 서랍 안에 넣을게요, 그다음 충전기 쪽으로 갈게요. 맞아요?",
          "en": "I will open the kitchen drawer, then put the foil in the kitchen drawer, then go to the living room "
                "charging dock. Is that right?"}[L]
    ep = _ep("shared_flat", 7189, "adult", L, G038, R038[L])
    r, log = _ask(ep, ok, L)
    assert r.kind == "yes", (r.text, log)
