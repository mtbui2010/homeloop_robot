"""Question classification and answer rendering in English and Korean (DESIGN 5.2, docs/user_model.md).

The simulated user reads the robot's question, finds which candidates (task ``user.candidates``) or world
objects it mentions, and picks the content of the answer. ``user.py`` then applies the answer-correctness mix,
patience, latency and ASR noise.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

WH_EN = ("which", "what", "where", "who", "whom", "whose", "how", "when")
WH_KO = ("어느", "어떤", "어디", "누구", "뭐", "무엇", "무슨", "어떻게", "몇", "언제")
WHERE = {"en": ("where",), "ko": ("어디",)}
AUX_EN = ("do", "does", "did", "is", "are", "was", "were", "should", "shall", "can", "could", "would", "will",
          "may", "might", "must", "have", "has")
YESNO_KO = ("까요?", "나요?", "가요?", "죠?", "니?", "맞아요?", "맞죠?", "할까?", "요?", "까?")

TEXT = {
    "not_sure": {"en": "I'm not sure what you mean.", "ko": "무슨 말씀인지 잘 모르겠어요."},
    "dont_know": {"en": "I don't know.", "ko": "잘 모르겠어요."},
    "yes": {"en": "Yes, that one.", "ko": "네, 맞아요."},
    "no": {"en": "No, ", "ko": "아니요, "},
    "help_ok": {"en": "OK, I moved it.", "ko": "치웠어요."},
    "stop": {"en": "Stop, please stop.", "ko": "잠깐, 멈춰 주세요."},
    "on": {"en": "It's on the {place}.", "ko": "{place} 위에 있어요."},
    "in": {"en": "It's in the {place}.", "ko": "{place} 안에 있어요."},
    "robot": {"en": "You are holding it.", "ko": "지금 들고 있잖아요."},
    "person": {"en": "{person} has it.", "ko": "{person}한테 있어요."},
    "candidate": {"en": "The {mention}.", "ko": "{mention}요."},
}


@dataclass(frozen=True)
class Content:
    """What the user means to say before the correctness mix: kind, text, whether it is informative (so the
    correct / not-sure / wrong mix applies), and the text of a wrong answer when one exists."""
    kind: str  # correct | yes | no | not_sure
    text: str
    informative: bool
    wrong_text: str | None = None
    rule: str = ""


# ------------------------------------------------------------------------------------ text helpers
def normalize(text: str, lang: str) -> str:
    t = unicodedata.normalize("NFC", text).lower()
    t = re.sub(r"[^\w\s']", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if lang == "ko":
        t = t.replace(" ", "")
    return t


def mentions(text: str, phrase: str, lang: str) -> bool:
    q, m = normalize(text, lang), normalize(phrase, lang)
    if not m:
        return False
    if lang == "ko":
        return m in q
    return f" {m} " in f" {q} "


def detect_lang(text: str) -> str:
    return "ko" if any("가" <= ch <= "힣" for ch in text) else "en"


def classify(question: str, lang: str | None = None) -> str:
    """wh | yes_no | other (DESIGN 5.2 rule 2)."""
    lang = lang or detect_lang(question)
    if lang == "ko":
        q = unicodedata.normalize("NFC", question).strip()
        if any(w in q for w in WH_KO):
            return "wh"
        q2 = q.replace(" ", "")
        if any(q2.endswith(e) for e in YESNO_KO):
            return "yes_no"
        return "other"
    words = normalize(question, "en").split()
    if not words:
        return "other"
    if any(w in WH_EN for w in words):
        return "wh"
    if words[0] in AUX_EN or question.strip().endswith("?"):
        return "yes_no"
    return "other"


def lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s and not s.startswith("I ") and not s.startswith("I'") else s


# ------------------------------------------------------------------------------------ world names
def object_names(world: Any, oid: str, lang: str) -> list[str]:
    """Names a person may use for an object: class name, colour + class name (longest first)."""
    obj = world.objects[oid]
    names: list[str] = []
    base = None
    nm = getattr(obj, "name", None)
    if isinstance(nm, dict):
        base = nm.get(lang)
    if base is None:
        try:
            from homeloop_robot.catalog import CLASSES, class_names  # robot core
            base = CLASSES[obj.cls].name[lang]
            names.extend(class_names(obj.cls, lang))
        except (ImportError, KeyError):
            base = obj.cls.replace("_", " ")
    names.append(base)
    color = (getattr(obj, "attrs", {}) or {}).get("color")
    if color:
        cname = color
        try:
            from homeloop_robot.catalog import COLORS
            cname = COLORS[color][lang]
        except (ImportError, KeyError):
            pass
        names.extend(f"{cname} {n}" for n in list(names))
    return sorted(set(names), key=lambda s: (-len(s), s))


def place_name(world: Any, pid: str, lang: str) -> str:
    pl = world.house.places.get(pid)
    if pl is None:
        if pid.startswith("floor@"):
            return {"en": "floor", "ko": "바닥"}[lang]
        return pid
    return pl.name.get(lang, pl.name.get("en", pid))


def person_name(world: Any, pid: str, lang: str) -> str:
    p = world.people.get(pid)
    if p is None:
        return pid
    return p.name.get(lang, p.name.get("en", pid))


def mentioned_objects(world: Any, question: str) -> list[str]:
    """Object ids whose most specific name appears in the question (both languages)."""
    hits: dict[str, int] = {}
    for oid in sorted(world.objects):
        for lang in ("en", "ko"):
            for n in object_names(world, oid, lang):
                if mentions(question, n, lang):
                    hits[oid] = max(hits.get(oid, 0), len(normalize(n, lang)))
    if not hits:
        return []
    best = max(hits.values())
    return sorted(o for o, n in hits.items() if n == best)


def location_text(world: Any, oid: str, lang: str) -> str:
    at = world.objects[oid].at
    if at == "robot":
        return TEXT["robot"][lang]
    if at.startswith("person:"):
        return TEXT["person"][lang].format(person=person_name(world, at.split(":", 1)[1], lang))
    key = "in" if getattr(world.objects[oid], "inside", False) else "on"
    return TEXT[key][lang].format(place=place_name(world, at, lang))


def candidate_text(cand: dict, lang: str) -> str:
    m = (cand.get("mentions") or {}).get(lang) or [cand.get("id", "")]
    return TEXT["candidate"][lang].format(mention=m[0])


# ------------------------------------------------------------------------------------ answer content
def compose(question: str, answer_lang: str, spec: dict | None, world: Any, *, knows_location: bool,
            other_place: str | None = None) -> Content:
    """Answer content for ``question`` (DESIGN 5.2 rules 3-4), before the correctness mix.

    ``knows_location``: whether the user knows where an asked-about object is (drawn by the caller);
    ``other_place``: a place id used for a wrong location answer.
    """
    qtype = classify(question)
    L = answer_lang
    spec = spec or {}
    cands = spec.get("candidates") or []
    ans = spec.get("answer")

    def in_any_lang(phrases: dict) -> bool:
        return any(mentions(question, p, lg) for lg in ("en", "ko") for p in (phrases or {}).get(lg, []))

    # clarification with candidates
    if cands and ans:
        intended = spec.get("intended")
        hit = [c for c in cands if in_any_lang(c.get("mentions"))]
        others = [c for c in cands if c.get("id") != intended]
        wrong = candidate_text(others[0], L) if others else None
        if qtype == "yes_no" and len(hit) == 1:
            if hit[0].get("id") == intended:
                return Content("yes", TEXT["yes"][L], True,
                               TEXT["no"][L] + lower_first(wrong) if wrong else None, "yes_no_intended")
            return Content("no", TEXT["no"][L] + lower_first(ans[L]), True, TEXT["yes"][L], "yes_no_other")
        if qtype == "wh" or len(hit) >= 2:
            return Content("correct", ans[L], True, wrong, "clarify_answer")
    # a resolution the task scripts (safety clarification, confirmation of a refused request)
    if ans and not cands and qtype in ("wh", "yes_no"):
        wt = spec.get("wrong_answer")
        return Content("correct", ans[L], True, wt[L] if isinstance(wt, dict) else None, "scripted_answer")
    # location question about an object
    if qtype == "wh" and any(mentions(question, w, lg) for lg in ("en", "ko") for w in WHERE[lg]):
        objs = mentioned_objects(world, question)
        if len(objs) > 1 and spec.get("intended") in objs:
            objs = [spec["intended"]]
        if len(objs) == 1:
            if not knows_location:
                return Content("not_sure", TEXT["dont_know"][L], False, None, "location_unknown")
            wrong = None
            if other_place is not None:
                key = "on"
                pl = world.house.places.get(other_place)
                if pl is not None and getattr(pl, "kind", "") == "container":
                    key = "in"
                wrong = TEXT[key][L].format(place=place_name(world, other_place, L))
            return Content("correct", location_text(world, objs[0], L), True, wrong, "location")
    if not spec:
        return Content("not_sure", TEXT["dont_know"][L], False, None, "generic_user")
    return Content("not_sure", TEXT["not_sure"][L], False, None, "not_understood")
