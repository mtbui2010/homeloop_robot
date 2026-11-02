"""SimUser: answer mix, patience, hearing, latency, motion, handover, interruptions, determinism."""
import math

import pytest

from _hs_helpers import FakeWorld, Streams, core_profile, load_params, world_available
from homeloop_robot.user import SimUser
from test_dialog import SPEC

NEAR = (1.5, 3.6)  # 0.67 m from grandma, living room


def user(name="real", spec=SPEC, lang="en", seed=0, world=None, **ov):
    return SimUser(world or FakeWorld(), load_params(name, **ov), Streams(seed), lang, spec)


def test_ideal_always_correct_and_static():
    u = user("ideal")
    for i in range(5):
        r, h = u.answer("Which mug, the red one or the blue one?", "en", NEAR, 10.0 * i)
        assert r.kind == "correct" and r.text == "The blue one." and h.text == r.text and h.event == "ok"
    p0 = u.people_at(0.0)
    p1 = u.people_at(1500.0)
    assert p0 == p1 and all(s.vel == (0.0, 0.0) for s in p1.values())
    assert u.interrupt_plan() is None


def test_answer_mix_matches_profile():
    n = 3000
    kinds = []
    for seed in range(n):
        u = user(seed=seed, **{"user.p_no_answer": 0.0})
        r, _ = u.answer("Which mug, the red one or the blue one?", "en", NEAR, 0.0)
        kinds.append(r.kind)
    p = load_params()
    assert kinds.count("wrong") / n == pytest.approx(p["user.answer.p_wrong"], abs=0.025)
    assert kinds.count("not_sure") / n == pytest.approx(p["user.answer.p_not_sure"], abs=0.02)
    assert kinds.count("correct") / n == pytest.approx(1 - 0.173 - 0.096, abs=0.03)


def test_wrong_answer_names_other_candidate():
    for seed in range(200):
        u = user(seed=seed, **{"user.answer.p_wrong": 1.0, "user.p_no_answer": 0.0})
        r, _ = u.answer("Which mug, the red one or the blue one?", "en", NEAR, 0.0)
        assert r.kind == "wrong" and r.text == "The red mug."


def test_korean_answers():
    u = user("ideal", lang="ko")
    r, h = u.answer("빨간 머그컵이요, 파란 머그컵이요?", "ko", NEAR, 0.0)
    assert r.text == "파란 거요." and h.text == "파란 거요."


def test_patience_then_silence():
    u = user("ideal")
    p = load_params("ideal")["user.patience_questions"]
    kinds = [u.answer("Which mug, the red one or the blue one?", "en", NEAR, float(i))[0].kind for i in range(p + 2)]
    assert kinds[:p] == ["correct"] * p and kinds[p:] == ["no_answer", "no_answer"]


def test_out_of_hearing_range():
    u = user("ideal", **{"user.dialog_channel": "voice"})
    r, h = u.answer("Which mug?", "en", (9.5, 4.5), 0.0)  # kitchen, 8.5 m away
    assert r.kind == "no_answer" and not r.heard_question and h.event == "not_heard"
    assert u.hears("grandma", (3.5, 6.0), 0.0)  # bedroom, 3.08 m away: within 3.6 m
    assert not u.hears("grandma", (9.5, 1.0), 0.0)
    assert u.hears("grandma", (9.5, 1.0), 0.0, broadcast=True)  # announce reaches the adjacent room


def test_asleep_person_does_not_answer():
    u = user("ideal", spec=dict(SPEC, asleep=["grandma"]))
    assert u.answer("Which mug?", "en", NEAR, 0.0)[0].kind == "no_answer"
    assert u.take_handover("grandma", "mug_2", 0.0)[0] is False


def test_latency_distribution():
    lats = []
    for seed in range(2000):
        u = user(seed=seed, **{"user.p_no_answer": 0.0})
        lats.append(u.answer("Which mug, the red one or the blue one?", "en", NEAR, 0.0)[0].latency_s)
    lats.sort()
    p = load_params()["user.latency"]
    assert min(lats) >= p["min"]
    assert lats[len(lats) // 2] == pytest.approx(p["median"], rel=0.08)
    assert sum(lats) / len(lats) == pytest.approx(7.1, rel=0.1)  # Zou et al.: mean 7.1 s


def test_help_reply():
    u = user("ideal")
    u.help_request("Could you move the box out of my way?", 3.0)
    r, _ = u.answer("Could you move the box out of my way?", "en", NEAR, 3.0)
    assert r.text == "OK, I moved it." and r.kind == "yes"


def test_location_answer_through_user():
    u = user("ideal", spec=None)
    r, _ = u.answer("Where is the phone?", "en", NEAR, 0.0)
    assert r.text == "It's on the coffee table."


def test_far_answer_uses_far_asr():
    u = user("real", **{"user.p_no_answer": 0.0, "asr.en.far_wer": 1.0, "asr.p_not_heard": 0.0,
                        "asr.p_partial": 0.0, "user.answer.p_wrong": 0.0, "user.answer.p_not_sure": 0.0,
                        "user.dialog_channel": "voice"})
    r, h = u.answer("Which mug, the red one or the blue one?", "en", (3.5, 2.5), 0.0)  # 3.0 m: far
    assert r.text == "The blue one." and h.event == "corrupted" and u.log[-1]["cond"] == "far"


def test_app_channel_reaches_the_user_anywhere_with_near_asr():
    u = user("real", **{"user.p_no_answer": 0.0, "asr.en.far_wer": 1.0, "asr.p_not_heard": 0.0,
                        "asr.p_partial": 0.0, "user.answer.p_wrong": 0.0, "user.answer.p_not_sure": 0.0,
                        "asr.en.near_wer": 0.0})
    assert u.dialog_channel == "app"
    far = (9.5, 4.5)                                 # kitchen, 8.5 m away: out of hearing range
    assert not u.hears("grandma", far, 0.0) and u.reachable(far, 0.0)
    assert u.ask_audience(far, 0.0) == ("grandma",)
    r, h = u.answer("Which mug, the red one or the blue one?", "en", far, 0.0)
    assert r.text == "The blue one." and h.event == "ok" and u.log[-1]["cond"] == "near"
    asleep = user("ideal", spec=dict(SPEC, asleep=["grandma"]))
    assert not asleep.reachable(NEAR, 0.0) and asleep.ask_audience(NEAR, 0.0) == ()
    assert user("ideal", **{"user.dialog_channel": "voice"}).ask_audience(far, 0.0) is None


def test_instruction_asr():
    u = user("ideal")
    assert u.hear_instruction("Bring the mug.", "en").text == "Bring the mug."
    u = user("real", **{"asr.en.near_wer": 1.0, "asr.p_not_heard": 0.0, "asr.p_partial": 0.0})
    assert u.hear_instruction("Bring the red mug please.", "en").event == "corrupted"


def test_motion_schedule_real():
    u = user("real", seed=3, **{"user.motion.rate_per_h": 20.0})
    walks = u.walks("grandma")
    assert walks, "with 20 walks/h some walk must happen within the horizon"
    w0 = walks[0]
    mid = (w0["t0"] + w0["t1"]) / 2
    st = u.people_at(mid)["grandma"]
    assert math.hypot(*st.vel) > 0
    assert u.people_at(w0["t1"] + 1.0)["grandma"].vel == (0.0, 0.0)
    # the walk takes path length / gait speed
    assert user("real", seed=3, **{"user.motion.rate_per_h": 20.0}).walks("grandma") == walks


def test_gait_speeds():
    u = user("ideal")
    p = load_params("ideal")
    # grandma 80-99 -> older-adult distribution, child -> child speed, both x indoor factor
    assert u._speed["child"] == pytest.approx(p["user.gait_child_mps"] * p["user.indoor_gait_factor"])
    lo, hi = p["user.gait_older"]["min"], p["user.gait_older"]["max"]
    assert lo * 0.7 - 1e-9 <= u._speed["grandma"] <= hi * 0.7 + 1e-9
    w = FakeWorld()
    w.people["grandma"].age_group = "30-39"
    u2 = SimUser(w, p, Streams(0), "en", None)
    assert u2._speed["grandma"] == pytest.approx(1.34 * 0.7)


def test_handover():
    u = user("ideal")
    ok, lat = u.take_handover("grandma", "mug_2", 0.0)
    assert ok and lat >= load_params()["user.handover_latency"]["min"]
    u = user("real", **{"user.p_unresponsive": 1.0})
    assert u.take_handover("grandma", "mug_2", 0.0) == (False, 60.0)


def test_interrupts():
    spec = dict(SPEC, interrupt={"after_calls": 3, "kind": "correction", "text": {"en": "Wait, the glass.",
                                                                                     "ko": "잠깐, 유리컵."},
                                 "new_goal": {"all": []}})
    u = user("ideal", spec=spec)
    assert u.interrupt_plan()["after_calls"] == 3
    assert u.interrupt_event(5.0).kind == "correction"
    u = user("real", **{"user.p_interrupt_stop": 1.0})
    plan = u.interrupt_plan()
    assert plan["kind"] == "stop" and 1 <= plan["after_calls"] <= 6 and plan["random"]
    assert u.events_between(0, 100) == []


def test_deterministic_and_seed_sensitive():
    def trace(seed):
        u = user(seed=seed, **{"user.motion.rate_per_h": 10.0})
        out = [u.answer("Which mug, the red one or the blue one?", "en", NEAR, float(i)) for i in range(5)]
        return out, u.people_at(900.0), u.interrupt_plan()
    assert trace(1) == trace(1)
    assert any(trace(1) != trace(s) for s in range(2, 8))


def test_bad_lang():
    with pytest.raises(ValueError):
        user(lang="vi")


@pytest.mark.skipif(not world_available(), reason="robot core world not present")
def test_simuser_on_core_houses():
    from homeloop_robot.houses import list_houses
    from homeloop_robot.rng import Streams as S
    from homeloop_robot.world import from_house
    prof = core_profile("real")
    for h in list_houses():
        for lang in ("en", "ko"):
            w = from_house(h, 1)
            u = SimUser(w, prof, S(1, "user-check"), lang, None)
            assert set(u.people_at(0.0)) == set(w.people)
            for pid in w.people:
                for t in (0.0, 600.0, 1700.0):
                    st = u.people_at(t)[pid]
                    assert st.room in w.house.rooms, (h, pid, t, st)
            uid = u.user_id
            assert w.people[uid].role == "user"
            near = tuple(w.people[uid].pos)
            oid = sorted(w.objects)[0]
            r, _ = u.answer({"en": "Where is the {n}?", "ko": "{n} 어디 있어요?"}[lang].format(
                n=__import__("homeloop_robot.dialog", fromlist=["x"]).object_names(w, oid, lang)[0]), lang, near, 0.0)
            assert r.kind in ("correct", "not_sure", "no_answer", "wrong")


def test_consistency_rows_pass():
    from homeloop_robot.user import consistency
    rows = consistency(FakeWorld(), load_params("real"), n=4000, seed=1)
    assert {r["param"] for r in rows} == {"user.p_no_answer", "user.answer.p_wrong", "user.answer.p_not_sure"}
    assert all(r["ok"] for r in rows), rows
    rows = consistency(FakeWorld(), load_params("ideal"), n=500, seed=1, lang="ko")
    assert all(r["ok"] and r["observed"] == 0 for r in rows), rows


def test_consistency_detects_a_wrong_rate():
    from homeloop_robot._hs_compat import binomial_row
    assert not binomial_row("x", 0.1, 300, 2000)["ok"]
    assert binomial_row("x", 0.1, 200, 2000)["ok"]


def test_where_are_you_through_user():
    u = user("ideal", spec=None)
    r, _ = u.answer("Where are you?", "en", NEAR, 0.0)
    seat = u.world.people[u.user_id].seat
    from homeloop_robot.dialog import place_name
    assert r.kind == "correct" and r.text == f"I'm at the {place_name(u.world, seat, 'en')}." and u.log[-1]["why"] == "self_position"
    w = user("real", seed=3, **{"user.motion.rate_per_h": 20.0})
    pid = "grandma"
    walk = w.walks(pid)[0]
    assert w.place_of(pid, (walk["t0"] + walk["t1"]) / 2) == (walk["to"], True)
    assert w.place_of(pid, walk["t1"] + 0.5) == (walk["to"], False)
