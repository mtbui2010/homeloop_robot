"""ASR noise: events, calibrated error rates, Korean syllables, determinism."""
import random

import pytest

from _hs_helpers import load_params
from homeloop_robot.asr import ASRRates, corrupt, is_hangul, ko_confuse, token_error_rate

EN = "could you please bring the red mug from the kitchen counter to grandma in the living room"
KO = "부엌 조리대에 있는 빨간 머그컵을 거실에 계신 할머니께 가져다 주세요"


def rates(name="real", **ov):
    return ASRRates(load_params(name, **ov))


def test_ideal_is_noise_free():
    r = rates("ideal")
    for i in range(200):
        for text, lang in ((EN, "en"), (KO, "ko")):
            for cond in ("near", "far"):
                h = corrupt(text, lang, cond, random.Random(i), r)
                assert h.text == text and h.event == "ok"


def test_event_rates_match_profile():
    r = rates()
    n = 20000
    ev = [corrupt(EN, "en", "near", random.Random(i), r).event for i in range(n)]
    assert ev.count("not_heard") / n == pytest.approx(0.0270, abs=0.004)
    assert ev.count("partial") / n == pytest.approx(0.0114, abs=0.003)


@pytest.mark.parametrize("lang,text,cond,key", [
    ("en", EN, "near", "asr.en.near_wer"), ("en", EN, "far", "asr.en.far_wer"),
    ("ko", KO, "near", "asr.ko.near_cer"), ("ko", KO, "far", "asr.ko.far_cer"),
])
def test_token_error_rate_matches_wer_cer(lang, text, cond, key):
    r = rates(**{"asr.p_not_heard": 0.0, "asr.p_partial": 0.0})
    target = load_params()[key]
    errs = [token_error_rate(text, corrupt(text, lang, cond, random.Random(i), r).text, lang) for i in range(1500)]
    mean = sum(errs) / len(errs)
    # edit distance can merge neighbouring edits, so allow a modest band around the per-token rate
    assert target * 0.75 <= mean <= target * 1.15, (mean, target)


def test_partial_keeps_prefix():
    r = rates(**{"asr.p_not_heard": 0.0, "asr.p_partial": 1.0})
    h = corrupt(EN, "en", "near", random.Random(3), r)
    assert h.event == "partial"
    words = EN.split()
    kept = h.text.split()
    assert len(kept) >= len(words) / 2 and kept == words[:len(kept)] and len(kept) < len(words)


def test_not_heard_and_empty():
    r = rates(**{"asr.p_not_heard": 1.0})
    assert corrupt(EN, "en", "far", random.Random(0), r).text == ""
    assert corrupt("   ", "en", "far", random.Random(0), rates()).event == "not_heard"


def test_condition_threshold():
    r = rates()
    assert r.condition(0.57) == "near" and r.condition(1.2) == "near" and r.condition(1.21) == "far"


def test_korean_confusions_stay_hangul():
    rng = random.Random(0)
    from homeloop_robot.asr import is_common_syllable
    for ch in "컵물약칼부엌조리대에있는빨간머그가져다주세요":
        for _ in range(20):
            c = ko_confuse(ch, rng)
            assert c == "" or (is_hangul(c) and is_common_syllable(c) and c != ch)
    assert is_common_syllable("가") and not is_common_syllable("앜") and not is_common_syllable("a")
    r = rates(**{"asr.ko.far_cer": 0.9, "asr.p_not_heard": 0.0, "asr.p_partial": 0.0})
    h = corrupt(KO, "ko", "far", random.Random(5), r)
    assert h.event == "corrupted" and h.text != KO


def test_deterministic():
    r = rates()
    a = [corrupt(EN, "en", "far", random.Random(i), r) for i in range(50)]
    b = [corrupt(EN, "en", "far", random.Random(i), r) for i in range(50)]
    assert a == b


def test_bad_args():
    with pytest.raises(ValueError):
        corrupt(EN, "fr", "near", random.Random(0), rates())
    with pytest.raises(ValueError):
        corrupt(EN, "en", "mid", random.Random(0), rates())


def test_token_error_rate():
    assert token_error_rate("a b c", "a b c", "en") == 0
    assert token_error_rate("a b c", "a x c", "en") == pytest.approx(1 / 3)
    assert token_error_rate("머그컵", "머그캅", "ko") == pytest.approx(1 / 3)


def test_consistency_rows_pass():
    from homeloop_robot.asr import consistency
    rows = consistency(load_params("real"), n=4000, seed=2)
    assert len(rows) == 8 and all(r["ok"] for r in rows), rows
    rows = consistency(load_params("ideal"), n=300, seed=2)
    assert all(r["ok"] and r["observed"] == 0 for r in rows), rows


def test_english_substitutions_are_real_words():
    from homeloop_robot.asr import CONFUSIONS_EN, FILLERS, VOCAB_EN, en_confuse
    real = set(VOCAB_EN) | {w for v in CONFUSIONS_EN.values() for x in v for w in x.split()} | set(FILLERS["en"])
    rng = random.Random(0)
    for w in EN.split() + ["don't", "know", "grandmother", "xylophone"]:
        for _ in range(10):
            out = en_confuse(w, rng)
            assert all(tok in real for tok in out.split()), (w, out)
            assert out != w
    r = rates(**{"asr.en.far_wer": 0.9, "asr.p_not_heard": 0.0, "asr.p_partial": 0.0})
    for i in range(50):
        h = corrupt(EN, "en", "far", random.Random(i), r)
        orig = set(EN.split())
        assert all(tok in real or tok in orig for tok in h.text.split()), h.text


def test_app_near_field_rates_and_corruption_share():
    from homeloop_robot.asr import ASRRates, corruption_share, corrupt
    from homeloop_robot.profiles import load_profile
    real = load_profile("real")
    r = ASRRates(real)
    assert r.rate[("ko", "app")] == 0.0521 and r.rate[("en", "app")] == 0.044
    assert r.rate[("ko", "app")] < r.rate[("ko", "near")]
    assert ASRRates(load_profile("ideal")).rate[("ko", "app")] == 0.0
    import random
    assert corrupt("컵 가져다 주세요", "ko", "app", random.Random(0), ASRRates(load_profile("ideal"))).event == "ok"
    texts = ["빨간 머그컵을 거실 탁자에 가져다 주세요"] * 400
    near = corruption_share(texts, "ko", real, "near", seed=1)
    app = corruption_share(texts, "ko", real, "app", seed=1, entities=[[["머그컵"]]] * 400)
    assert app["changed"] < near["changed"] and 0.0 < app["entity_changed"] < app["changed"]
    assert corruption_share(texts, "ko", real, "app", seed=1) == corruption_share(texts, "ko", real, "app", seed=1)
