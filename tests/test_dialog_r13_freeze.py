"""r12 / r13 simulator freeze (homeloop_bench docs/experiments.md, Round 11 gate decisions, simulated-user bugs S1-S8):
eight consistency fixes found by the per-task analysis of the n=50 gate. Worlds: the gate tasks' houses and start
states. No rate or scoring value changed."""
import pytest

from homeloop_robot.episode import make_episode
from helpers import patched


def _ep(house, seed_state, L, goal, request, profile="ideal", seed=0):
    ep = make_episode(house, seed_state, profile, seed, lang=L, user_spec={"persona": "adult"}, key="r13")
    ep.user.hear_instruction(request, L)
    ep.user.set_wants(goal)
    return ep


def _ask(ep, q, L, meaning=None):
    r, _h = ep.user.answer(q, L, tuple(ep.world.person_xy(ep.user.user_id)), 1.0, meaning=meaning)
    return r, ep.user.log[-1]


# ── S1: hl-dev-000037, "the red one or the blue one" is a choice between two books ───────────────────────────────
G037 = {"all": [{"pred": "delivered", "args": ["book_1", "grandma"], "mode": "reach"}]}
R037 = {"en": "If the red book is on the coffee table, bring it to me; if not, bring me the blue book instead.",
        "ko": "거실 탁자에 빨간 책이 있으면 갖다주고, 없으면 파란 책을 대신 갖다줘요."}


@pytest.mark.parametrize("q", ["Which book do you want me to bring you, the red one or the blue one?",
                               "Which book should I bring you, the red one or the blue one?",
                               "Which book do you want, the red one or the blue one?",
                               "Should I bring the red one or the blue one?"])
def test_s1_the_red_one_or_the_blue_one_is_which_object(q):
    ep = _ep("senior_flat", 1859, "en", G037, R037["en"])
    r, log = _ask(ep, q, "en")
    assert r.text == "The red book." and log["why"] == "goal_object", (r.text, log)


@pytest.mark.parametrize("q", ["어떤 책을 가져다 드릴까요, 빨간 거 아니면 파란 거요?",
                               "어떤 책을 드릴까요, 빨간 것이요, 파란 것이요?"])
def test_s1_ko_the_red_one_or_the_blue_one(q):
    ep = _ep("senior_flat", 1859, "ko", G037, R037["ko"])
    r, log = _ask(ep, q, "ko")
    assert r.text == "빨간 책요." and log["why"] == "goal_object", (r.text, log)


# ── S2: hl-dev-000003 KO, a read-back tagged "맞는 거죠?" ─────────────────────────────────────────────────────────
G003 = {"all": [{"pred": "in", "args": ["milk_1", "kimchi_fridge@kitchen"]}]}


@pytest.mark.parametrize("tag", ["맞는 거죠?", "맞는 건가요?", "맞죠?", "맞아요?"])
def test_s2_a_correct_ko_readback_is_confirmed_whatever_the_tag(tag):
    ep = _ep("korean_apt_59", 7132, "ko", G003, "우유를 넣어 둘래요?")
    r, log = _ask(ep, "우유 김치냉장고 안에 넣을게요. " + tag, "ko")
    assert r.kind == "yes", (r.text, log)


def test_s2_a_wrong_ko_readback_with_the_same_tag_is_corrected():
    ep = _ep("korean_apt_59", 7132, "ko", G003, "우유를 넣어 둘래요?")
    r, log = _ask(ep, "우유 냉장고 안에 넣을게요. 맞는 거죠?", "ko")
    assert r.kind == "no", (r.text, log)


# ── S3: hl-dev-000033 KO, 폰 is a name of the phone ───────────────────────────────────────────────────────────────
G033 = {"all": [{"pred": "on", "args": ["phone_1", "sofa@living"]}]}


def test_s3_pon_is_the_phone():
    from homeloop_robot import dialog as D
    ep = _ep("shared_flat", 9504, "ko", G033, "휴대폰 소파에 갖다 놔 주세요.")
    assert D.mentions("검은 폰", "폰", "ko") and "폰" in D.object_names(ep.world, "phone_1", "ko")
    r, log = _ask(ep, "사이드 테이블에 있는 폰 소파에 놓을게요. 맞죠?", "ko")
    r2, log2 = _ask(ep, "사이드 테이블에 있는 휴대폰 소파에 놓을게요. 맞죠?", "ko")
    assert r.kind == "yes" and r2.kind == "yes", (r.text, r2.text, log, log2)


# ── S4: hl-dev-000048, "the mug from the charger" is not the dock ────────────────────────────────────────────────
G048 = {"all": [{"pred": "on", "args": ["book_1", "desk@small"]}, {"pred": "held_by", "args": ["mug_1", "user"], "mode": "reach"},
                {"pred": "docked", "args": []}]}
R048 = {"en": "Put the red book on the desk, then bring me the white mug. After that, go back and charge.",
        "ko": "빨간 책 좀 책상에 갖다 놔 주고, 하얀 머그컵 갖다주세요. 그다음에 충전하러 돌아가도 돼요."}
RB048 = {"en": ("I will put the red book on the desk, then bring you the mug from the charger. Is that right?",
                "I will put the red book on the desk, then bring you the mug that is at the charging dock. Is that right?"),
         "ko": ("빨간 책 책상 위에 놓을게요, 그다음 충전기에 있는 머그 저한테 드릴게요. 맞죠?",
                "빨간 책 책상 위에 놓을게요, 그다음 충전기에서 가져온 머그 저한테 드릴게요. 맞죠?")}


@pytest.mark.parametrize("L", ["en", "ko"])
def test_s4_a_dock_word_that_places_an_object_is_not_the_dock_step(L):
    for rb in RB048[L]:
        ep = _ep("korean_apt_59", 5665, L, G048, R048[L])
        r, log = _ask(ep, rb, L)
        assert r.kind == "no" and log["why"] == "goal_correct", (rb, r.text, log)


def test_s4_a_read_back_that_goes_to_the_dock_is_still_confirmed():
    for L, rb in (("en", "I will put the red book on the desk, then bring you the white mug from the table, then go to "
                         "the charging dock. Is that right?"),
                  ("ko", "빨간 책 책상 위에 놓을게요, 그다음 머그 저한테 드릴게요, 그다음 충전기로 갈게요. 맞죠?")):
        ep = _ep("korean_apt_59", 5665, L, G048, R048[L])
        r, log = _ask(ep, rb, L)
        assert r.kind == "yes", (rb, r.text, log)


# ── S5: hl-dev-000038 KO, '충전기 말씀하셨는데, 거기서 뭘 할까요?' reads like the English two sentences ───────────
G038 = {"all": [{"pred": "open", "args": ["drawer@kitchen"]}, {"pred": "in", "args": ["foil_1", "drawer@kitchen"]},
                {"pred": "docked", "args": []}]}
R038 = {"ko": "주방 서랍을 열어서 쿠킹포일을 안에 넣어 주시겠어요? 다 마치시면 충전기로 이동해 주세요.",
        "en": "Open the kitchen drawer and stick the aluminum foil inside, then head back to your charger."}


@pytest.mark.parametrize("L,q", [("ko", "충전기 말씀하셨는데, 거기서 뭘 할까요?"),
                                 ("en", "You mentioned the charging dock. What should I do there?")])
def test_s5_a_mentioned_place_question_asks_for_the_request_again(L, q):
    ep = _ep("shared_flat", 7189, L, G038, R038[L])
    r, log = _ask(ep, q, L)
    assert log["why"] == "repeat_request" and r.text == R038[L], (r.text, log)


# ── S6: the help reply carries an acknowledgement word in Korean as in English ───────────────────────────────────
def test_s6_help_reply_has_an_acknowledgement_in_both_languages():
    from homeloop_robot import dialog as D
    assert D.TEXT["help_ok"]["en"].startswith("OK")
    assert D.TEXT["help_ok"]["ko"].startswith("네")
