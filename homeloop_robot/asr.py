"""ASR noise for English and Korean (DESIGN 5.3, docs/user_model.md).

Per utterance: ``not_heard`` with ``asr.p_not_heard``, ``partial`` with ``asr.p_partial`` (only the first half
or more of the tokens survive), else every token is corrupted independently with probability WER (English,
per word) or CER (Korean, per Hangul syllable). A corrupted token is substituted, deleted, or followed by an
inserted filler, in the proportions ``asr.op_shares``. Rates come from the profile; the defaults in the
``real`` profile are Whisper large-v2 numbers (Radford et al., arXiv:2212.04356, Table 2; Park et al.,
arXiv:2410.18444, Table 3) and in-home older-adult breakdown rates (Mahmood et al., arXiv:2403.02421, Table 2).
"""
from __future__ import annotations

import math
import random
import re
from typing import Any

from homeloop_robot._hs_compat import Heard, param

PARAMS = (
    "asr.en.near_wer",
    "asr.en.far_wer",
    "asr.ko.near_cer",
    "asr.ko.far_cer",
    "asr.p_not_heard",
    "asr.p_partial",
    "asr.far_threshold_m",
    "asr.op_shares",
)

# Near-homophone confusions (a small hand list; substitutions outside it change one vowel).
CONFUSIONS_EN = {
    "cup": ["cop", "cap"], "mug": ["mud", "bug"], "red": ["bread", "read"], "blue": ["glue", "blew"],
    "glass": ["grass", "class"], "plate": ["plane", "play"], "fork": ["fort", "pork"], "knife": ["night", "life"],
    "spoon": ["soon", "moon"], "bowl": ["ball", "bold"], "towel": ["tower", "trowel"], "book": ["look", "cook"],
    "remote": ["remove", "promote"], "phone": ["fone", "foam"], "keys": ["knees", "keeps"], "pill": ["bill", "peel"],
    "pills": ["bills", "peels"], "bottle": ["model", "battle"], "drawer": ["draw", "door"], "fridge": ["bridge", "fringe"],
    "shelf": ["self", "shell"], "table": ["cable", "label"], "sink": ["think", "zinc"], "bed": ["bad", "bet"],
    "box": ["books", "fox"], "milk": ["silk", "milt"], "water": ["waiter", "daughter"], "kitchen": ["chicken", "kitten"],
    "living": ["giving", "leaving"], "bedroom": ["bathroom", "bed room"], "bathroom": ["bedroom", "bath room"],
    "yes": ["yet", "us"], "no": ["know", "now"], "left": ["lift", "loft"], "right": ["write", "light"],
    "green": ["clean", "grin"], "black": ["back", "block"], "white": ["wide", "write"], "one": ["won", "on"],
}
FILLERS = {"en": ["uh", "um", "the", "a"], "ko": ["어", "음", "그"]}
_VOWELS_EN = "aeiou"

# Hangul syllable arithmetic: S = 0xAC00 + (L * 21 + V) * 28 + T
_H0, _H1 = 0xAC00, 0xD7A3
_KO_VOWEL_NEIGHBOURS = {0: [4, 1], 1: [5, 0], 4: [0, 5], 5: [1, 4], 8: [13, 18], 13: [8, 18], 18: [20, 13],
                        20: [18, 8], 2: [6], 6: [2], 12: [17], 17: [12]}


def is_hangul(ch: str) -> bool:
    return len(ch) == 1 and _H0 <= ord(ch) <= _H1


def ko_confuse(ch: str, rng: random.Random) -> str:
    """A near-homophone of one Hangul syllable: neighbouring vowel, or the final consonant dropped/added."""
    code = ord(ch) - _H0
    lead, rest = divmod(code, 21 * 28)
    vowel, tail = divmod(rest, 28)
    if rng.random() < 0.6 and vowel in _KO_VOWEL_NEIGHBOURS:
        vowel = rng.choice(_KO_VOWEL_NEIGHBOURS[vowel])
    elif tail:
        tail = 0
    else:
        tail = rng.choice([4, 8, 21])  # ㄴ ㄹ ㅇ
    return chr(_H0 + (lead * 21 + vowel) * 28 + tail)


def en_confuse(word: str, rng: random.Random) -> str:
    core = re.sub(r"[^\w']", "", word.lower())
    if core in CONFUSIONS_EN:
        return rng.choice(CONFUSIONS_EN[core])
    idx = [i for i, c in enumerate(core) if c in _VOWELS_EN]
    if not idx:
        return core + "s" if core else word
    i = rng.choice(idx)
    repl = rng.choice([v for v in _VOWELS_EN if v != core[i]])
    return core[:i] + repl + core[i + 1:]


class ASRRates:
    def __init__(self, profile: Any):
        g = lambda n: param(profile, n)  # noqa: E731
        self.rate = {("en", "near"): float(g("asr.en.near_wer")), ("en", "far"): float(g("asr.en.far_wer")),
                     ("ko", "near"): float(g("asr.ko.near_cer")), ("ko", "far"): float(g("asr.ko.far_cer"))}
        self.p_not_heard = float(g("asr.p_not_heard"))
        self.p_partial = float(g("asr.p_partial"))
        self.far_threshold_m = float(g("asr.far_threshold_m"))
        ops = dict(g("asr.op_shares"))
        tot = sum(ops.values())
        self.ops = {k: (ops[k] / tot if tot > 0 else 0.0) for k in ("sub", "del", "ins")}

    def condition(self, distance_m: float) -> str:
        return "near" if distance_m <= self.far_threshold_m else "far"


def _op(rng: random.Random, ops: dict) -> str:
    u = rng.random()
    acc = 0.0
    for k in ("sub", "del", "ins"):
        acc += ops[k]
        if u < acc:
            return k
    return "sub"


def corrupt(text: str, lang: str, condition: str, rng: random.Random, rates: ASRRates) -> Heard:
    """What the robot's ASR hears for ``text`` spoken in ``lang`` under ``condition`` (near | far)."""
    if lang not in ("en", "ko"):
        raise ValueError(f"lang must be en or ko, not {lang!r}")
    if condition not in ("near", "far"):
        raise ValueError(f"condition must be near or far, not {condition!r}")
    if not text.strip():
        return Heard("", "not_heard")
    u = rng.random()
    if u < rates.p_not_heard:
        return Heard("", "not_heard")
    tokens = text.split()
    if u < rates.p_not_heard + rates.p_partial and len(tokens) >= 2:
        keep = rng.randint(math.ceil(len(tokens) / 2), len(tokens) - 1)
        return Heard(" ".join(tokens[:keep]), "partial")
    p = rates.rate[(lang, condition)]
    if p <= 0:
        return Heard(text, "ok")
    changed = False
    if lang == "en":
        out: list[str] = []
        for w in tokens:
            if rng.random() < p:
                changed = True
                op = _op(rng, rates.ops)
                if op == "sub":
                    out.append(en_confuse(w, rng))
                elif op == "ins":
                    out.extend([w, rng.choice(FILLERS["en"])])
            else:
                out.append(w)
            # deletion: nothing appended
        return Heard(" ".join(out), "corrupted" if changed else "ok")
    words_out = []
    for w in tokens:
        chars = []
        for ch in w:
            if is_hangul(ch) and rng.random() < p:
                changed = True
                op = _op(rng, rates.ops)
                if op == "sub":
                    chars.append(ko_confuse(ch, rng))
                elif op == "ins":
                    chars.extend([ch, rng.choice(FILLERS["ko"])])
            else:
                chars.append(ch)
        if chars:
            words_out.append("".join(chars))
    return Heard(" ".join(words_out), "corrupted" if changed else "ok")


def token_error_rate(ref: str, hyp: str, lang: str) -> float:
    """WER (en, words) or CER (ko, characters without spaces) by edit distance; for tests and docs."""
    if lang == "ko":
        r, h = list(ref.replace(" ", "")), list(hyp.replace(" ", ""))
    else:
        r, h = ref.split(), hyp.split()
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        cur = [i] + [0] * len(h)
        for j in range(1, len(h) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r[i - 1] != h[j - 1]))
        prev = cur
    return prev[-1] / len(r)


def consistency(profile: Any, n: int = 20000, seed: int = 0) -> list[dict]:
    """Empirical ASR event and token-error rates vs the profile (DESIGN 13.3). One row per parameter."""
    from homeloop_robot._hs_compat import binomial_row, rng_for

    r = ASRRates(profile)
    rows = []
    long_text = {"en": "please bring the red mug to the kitchen", "ko": "빨간 머그컵을 부엌에 가져다 주세요"}
    nh = pa = 0
    for i in range(n):
        h = corrupt(long_text["en"], "en", "near", rng_for(seed, "asr-consistency", "event", i), r)
        nh += h.event == "not_heard"
        pa += h.event == "partial"
    rows.append(binomial_row("asr.p_not_heard", r.p_not_heard, nh, n, "per utterance"))
    rows.append(binomial_row("asr.p_partial", r.p_partial, pa, n, "per utterance (>= 2 tokens)"))
    token = {"en": "mug", "ko": "컵"}
    for lang, key in (("en", "wer"), ("ko", "cer")):
        for cond in ("near", "far"):
            hits = heard = 0
            for i in range(n):
                h = corrupt(token[lang], lang, cond, rng_for(seed, "asr-consistency", lang, cond, i), r)
                if h.event == "not_heard":
                    continue
                heard += 1
                hits += h.event == "corrupted"
            rows.append(binomial_row(f"asr.{lang}.{cond}_{key}", r.rate[(lang, cond)], hits, heard,
                                     f"per {'word' if lang == 'en' else 'syllable'}, heard tokens"))
    return rows
