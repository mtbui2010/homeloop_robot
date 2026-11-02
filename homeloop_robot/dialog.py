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
    "self_at": {"en": "I'm at the {place}.", "ko": "{place}에 있어요."},
    "self_going": {"en": "I'm going to the {place}.", "ko": "{place}{ro} 가고 있어요."},
}
# "where are you?": the robot asks the user's own position (e.g. to bring something to them)
SELF_WHERE = {"en": (r"\bwhere are you\b", r"\bwhere you are\b", r"\bwhere are you now\b"),
              "ko": (r"어디\s*에?\s*계", r"어디\s*세요", r"어디\s*계신")}


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
        # the question may be followed by a remark ("...TV대에요? 두 곳에 놓을 수는 없어요.")
        parts = [q2] + [seg + "?" for seg in q2.split("?")[:-1]]
        if any(p.endswith(e) for p in parts for e in YESNO_KO):
            return "yes_no"
        return "other"
    words = normalize(question, "en").split()
    if not words:
        return "other"
    if any(w in WH_EN for w in words):
        return "wh"
    if words[0] in AUX_EN or "?" in question:
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
        names.extend(f"{cname} {n}" for n in list(names) if not n.startswith(f"{cname} "))
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


def asks_user_position(question: str) -> bool:
    """Does the question ask where the user is ("Where are you?", "지금 어디에 계세요?")?"""
    q = unicodedata.normalize("NFC", str(question or "")).lower()
    return any(re.search(rx, q) for lg in ("en", "ko") for rx in SELF_WHERE[lg])


def _ro(word: str) -> str:
    """Korean directional particle: 로 after a vowel or ㄹ final, else 으로."""
    if not word:
        return "로"
    c = ord(word[-1]) - 0xAC00
    if not 0 <= c <= 11171:
        return "로"
    final = c % 28
    return "로" if final in (0, 8) else "으로"


def self_position_text(world: Any, place: str, moving: bool, lang: str) -> str:
    name = place_name(world, place, lang)
    if moving:
        return TEXT["self_going"][lang].format(place=name, ro=_ro(name))
    return TEXT["self_at"][lang].format(place=name)


def candidate_text(cand: dict, lang: str) -> str:
    m = (cand.get("mentions") or {}).get(lang) or [cand.get("id", "")]
    return TEXT["candidate"][lang].format(mention=m[0])


# ------------------------------------------------------------------------------------ answer content
def compose(question: str, answer_lang: str, spec: dict | None, world: Any, *, knows_location: bool,
            other_place: str | None = None, user_place: tuple | None = None,
            goal: "GoalView | None" = None) -> Content:
    """Answer content for ``question`` (DESIGN 5.2 rules 3-4), before the correctness mix.

    ``knows_location``: whether the user knows where an asked-about object is (drawn by the caller);
    ``other_place``: a place id used for a wrong location answer;
    ``user_place``: ``(place_id, moving)`` of the answering user, for "where are you?";
    ``goal``: what the user asked for (:class:`GoalView`), for questions about the request itself
    (:func:`compose_from_goal`); None = those questions are not understood.
    """
    qtype = classify(question)
    L = answer_lang
    spec = spec or {}
    cands = spec.get("candidates") or []
    ans = spec.get("answer")

    def in_any_lang(phrases: dict) -> bool:
        return any(mentions(question, p, lg) for lg in ("en", "ko") for p in (phrases or {}).get(lg, []))

    # "where are you?" (naming no candidate): the user says where they are (or where they are walking to); people
    # do not get their own position wrong, so the answer is not informative in the correctness-mix sense (ASR
    # still applies)
    if user_place is not None and qtype == "wh" and asks_user_position(question) and \
            not any(in_any_lang(c.get("mentions")) for c in cands):
        return Content("correct", self_position_text(world, user_place[0], bool(user_place[1]), L), False, None,
                       "self_position")
    # a clarification about WHICH object does not answer "where should it go?": that is the request itself
    if goal is not None and cands and spec.get("slot") == "object" and asks_destination(question):
        c = compose_from_goal(question, L, world, goal, knows_location=knows_location, other_place=other_place)
        if c is not None and c.rule == "goal_destination":
            return c
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
    # a question about the request itself: where an object goes, which one / which place, a read-back
    if goal is not None:
        c = compose_from_goal(question, L, world, goal, knows_location=knows_location, other_place=other_place)
        if c is not None:
            return c
    # location question about an object ("where is X?"; "where should I put X?" asks where it should go, not
    # where it is)
    ql = _q_text(question)
    dest_only = asks_destination(question) and not (LOC_RX["en"].search(ql.lower()) or LOC_RX["ko"].search(ql))
    if qtype == "wh" and not dest_only and (any(mentions(question, w, lg) for lg in ("en", "ko") for w in WHERE[lg])
                                            or re.search(r"\bwhich place\b[^?]*\b(look|find|search)\b", ql.lower())):
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


# ------------------------------------------------------------------------------------ answers from the user's goal
# The person who gave the task knows what they asked for. When the task's goal is known (``wants``: the goal atoms
# the user asked for, set by the runner), questions about that request get the answer a person gives: where an object
# they named should go, which of the named objects / places they meant, and whether a read-back of the plan is right
# ("I will put the mug on the counter. Is that right?" -> "Yes, that's right." / "No, put the mug in the sink.").
# Open questions ("What should I do?", "What else?") still get "not sure": the user restates their request, never
# extends it. The correctness / not-sure mix and ASR noise apply as for every informative answer (user.py).

GOAL_TEXT = {
    "on": {"en": "On the {place}, please.", "ko": "{place} 위에 놔 주세요."},
    "in": {"en": "In the {place}, please.", "ko": "{place} 안에 넣어 주세요."},
    "to_me": {"en": "Bring it to me, please.", "ko": "저한테 갖다 주세요."},
    "to_person": {"en": "Give it to {person}, please.", "ko": "{person}한테 갖다 주세요."},
    "pick": {"en": "The {name}.", "ko": "{name}요."},
    "yes": {"en": "Yes, that's right.", "ko": "네, 맞아요."},
    "no": {"en": "No.", "ko": "아니요."},
    "fix_on": {"en": "No, put the {obj} on the {place}.", "ko": "아니요, {obj}{eun} {place} 위에 놔 주세요."},
    "fix_in": {"en": "No, put the {obj} in the {place}.", "ko": "아니요, {obj}{eun} {place} 안에 넣어 주세요."},
    "fix_to_me": {"en": "No, bring the {obj} to me.", "ko": "아니요, {obj}{eun} 저한테 갖다 주세요."},
    "fix_to_person": {"en": "No, give the {obj} to {person}.", "ko": "아니요, {obj}{eun} {person}한테 갖다 주세요."},
    "fix_open": {"en": "No, open the {place}.", "ko": "아니요, {place}{eul} 열어 주세요."},
    "fix_close": {"en": "No, close the {place}.", "ko": "아니요, {place}{eul} 닫아 주세요."},
    "fix_go": {"en": "No, go to the {place}.", "ko": "아니요, {place}{ro} 가 주세요."},
    "fix_dock": {"en": "No, go back to the charger.", "ko": "아니요, 충전기로 돌아가 주세요."},
    "fix_say": {"en": "No, I asked you to tell {person}.", "ko": "아니요, {person}한테 말해 달라고 했어요."},
    "person_at": {"en": "{person} is at the {place}.", "ko": "{person}{eun} {place}에 있어요."},
}
# "where should I put / bring ... ?" (a destination), not "where is ...?" (a location)
DEST_RX = {"en": re.compile(r"\bwhere\b[^?]*\b(put|place[sd]?|leave|left|bring|brought|take|taken|move[sd]?|keep|kept|"
                            r"store[sd]?|stash(ed)?|go|goes|deliver(ed)?|hand|give|given|drop(ped)?|set)\b|"
                            r"\b(put|place|bring|take|leave|move|set)\b[^?]*\bwhere\b|"
                            r"\bwhat (should|do|shall) (i|you want me to) do with\b"),
           "ko": re.compile(r"어디\s*(에|에다|로|으로|다)?\s*(가)?\s*(두|둘|놓|놔|넣|가져|갖다|옮기|옮겨|드리|드릴|놓아|올려)|"
                           r"(어떻게|뭘|무엇을)\s*(해야|할까|하면)")}
LOC_RX = {"en": re.compile(r"\bwhere\b[^?]*\b(is|are)\b|\blocated\b|\b(where|which place)\b[^?]*\b(find|look|search)\b"),
          "ko": re.compile(r"어디\s*(에)?\s*(있|계)")}
WHICH_FOR_RX = re.compile(r"\bwhich place\b[^?]*\bfor the\b")       # "which place do you mean for the mug?"
SEARCH_RX = re.compile(r"\b(look|find|search)\b")
ALT_RX = re.compile(r"\bor\b|아니면|또는|이나|거나")
READBACK_RX = re.compile(r"\bI will\b|\bI'll\b|\bI'm going to\b|\bI am going to\b|겠습니다|게요|놓아요|둬요|넣어요|"
                         r"맞죠|맞나요|맞습니까")
ME_RX = {"en": re.compile(r"\b(you|your hand|to me|hand it|give it)\b"),
         "ko": re.compile(r"(드릴|드려|갖다\s*드|가져다\s*드|건네|손에)")}
DOCK_WORDS = ("dock", "charg", "충전")


def _final(word: str) -> bool:
    """Does the Korean word end in a consonant (batchim)?"""
    c = ord(word[-1]) - 0xAC00 if word else -1
    return 0 <= c <= 11171 and c % 28 != 0


def _ko(fmt: str, **kw) -> str:
    """Korean template with the particles 은/는 ({eun}), 을/를 ({eul}), (으)로 ({ro}) chosen by the word before them."""
    s = fmt.replace("{eun}", "\x01").replace("{eul}", "\x02").replace("{ro}", "\x03").format(**kw)
    out = []
    for ch in s:
        prev = "".join(out).rstrip()
        if ch == "\x01":
            out.append("은" if _final(prev) else "는")
        elif ch == "\x02":
            out.append("을" if _final(prev) else "를")
        elif ch == "\x03":
            out.append(_ro(prev.split()[-1] if prev.split() else ""))
        else:
            out.append(ch)
    return "".join(out)


def _say(key: str, L: str, **kw) -> str:
    fmt = GOAL_TEXT[key][L]
    return _ko(fmt, **kw) if L == "ko" else fmt.format(**kw)


def _q_text(question: str) -> str:
    """The question with plan keys spelled as words ('kimchi_fridge@kitchen' -> 'kimchi fridge in the kitchen')."""
    return str(question or "").replace("@", " in the ").replace("_", " ")


# English loanwords a Korean speaker hears as the same place ("카운터" for the counter): a robot's Korean read-back
# often uses them instead of the house's Korean name
KO_LOAN = {"counter": ["카운터"], "table": ["테이블"], "coffee table": ["커피 테이블"], "dining table": ["다이닝 테이블"],
           "desk": ["데스크"], "sofa": ["소파"], "sink": ["싱크"], "kitchen sink": ["싱크"], "fridge": ["냉장고"],
           "drawer": ["드로어"], "closet": ["클로젯"], "dresser": ["드레서"], "nightstand": ["나이트스탠드"],
           "armchair": ["암체어"], "tv stand": ["TV 스탠드", "티비 스탠드"], "bookshelf": ["북쉘프"],
           "shelf": ["쉘프"], "wall shelf": ["쉘프"], "microwave": ["마이크로웨이브"], "stove": ["스토브"],
           "dock": ["도크"], "charging dock": ["도크", "충전 도크"], "wardrobe": ["워드로브"], "bed": ["베드"],
           "toy box": ["토이 박스"], "recliner": ["리클라이너"], "side table": ["사이드 테이블"]}


def _place_words(world: Any, pid: str) -> list[str]:
    pl = world.house.places.get(pid)
    head = pid.split("@")[0].replace("_", " ")
    out = [head]
    if pl is not None:
        for lg in ("en", "ko"):
            out += [pl.name.get(lg, "")] + list(((getattr(pl, "aliases", None) or {}).get(lg)) or [])
    en = (pl.name.get("en", "") if pl is not None else "").lower()
    out += KO_LOAN.get(en, []) + KO_LOAN.get(head, [])
    return [w for w in dict.fromkeys(out) if w]


def _mentions_any(q: str, phrases) -> bool:
    return any(mentions(q, p, lg) for p in phrases for lg in ("en", "ko") if detect_lang(p) == lg)


def _person_words(world: Any, pid: str) -> list[str]:
    p = world.people.get(pid)
    if p is None:
        return []
    out = []
    for lg in ("en", "ko"):
        out += [p.name.get(lg, "")] + list(((getattr(p, "aliases", None) or {}).get(lg)) or [])
    return [w for w in out if w and w.lower() not in ("me", "나")]


def _obj_words(world: Any, oid: str) -> list[str]:
    return [n for lg in ("en", "ko") for n in object_names(world, oid, lg)]


def _specific_name(world: Any, oid: str, L: str) -> str:
    """The object's plain name with its colour ("red mug"), as a person names it."""
    obj = world.objects[oid]
    nm = getattr(obj, "name", None)
    base = nm.get(L) if isinstance(nm, dict) else None
    if base is None:
        try:
            from homeloop_robot.catalog import CLASSES
            base = CLASSES[obj.cls].name[L]
        except (ImportError, KeyError):
            base = obj.cls.replace("_", " ")
    color = (getattr(obj, "attrs", {}) or {}).get("color")
    if color:
        try:
            from homeloop_robot.catalog import COLORS
            color = COLORS[color][L]
        except (ImportError, KeyError):
            pass
        if not base.startswith(f"{color} "):
            base = f"{color} {base}"
    return base


def asks_destination(question: str) -> bool:
    """Does the question ask where something should go ("where should I put X?", "어디에 둘까요?")?"""
    q = _q_text(question)
    low = q.lower()
    return bool(DEST_RX["en"].search(low) or DEST_RX["ko"].search(q)
                or (WHICH_FOR_RX.search(low) and not SEARCH_RX.search(low)))


def _dest_answer(gv: "GoalView", objs: list, L: str) -> str:
    """Where each asked-about object goes; one sentence when they all go to the same place."""
    texts = [gv.dest_text(gv.dest(o), L) for o in objs[:2]]
    if len(set(texts)) == 1:
        return texts[0]
    if L == "ko":
        return " ".join(f"{_specific_name(gv.w, o, L)}{'은' if _final(_specific_name(gv.w, o, L)) else '는'} {t}"
                        for o, t in zip(objs, texts))
    return " ".join(f"The {_specific_name(gv.w, o, L)}: {t[:1].lower() + t[1:]}" for o, t in zip(objs, texts))


def _atoms(wants: dict | None) -> list[dict]:
    out = []
    for a in (wants or {}).get("all") or []:
        if "any" in a:
            places = [x["args"][0] for x in a["any"] if x.get("pred") == "robot_at"]
            if places:
                out.append({"pred": "robot_at_any", "args": places})
            continue
        if "not" in a or a.get("pred") == "unmoved":
            continue
        if a.get("pred") == "delivered":
            # what the user says about a delivery ("bring it to me") does not depend on reach / hand
            a = {"pred": "held_by", "args": list(a.get("args") or [])}
        out.append(a)
    return out


class GoalView:
    """What the user wants, readable against a question."""

    def __init__(self, world: Any, wants: dict | None, user_id: str | None, place_of=None):
        self.w = world
        self.atoms = _atoms(wants)
        self.user_id = user_id
        self.place_of = place_of or (lambda pid: getattr(world.people.get(pid), "seat", None))

    # the destination of an object the user asked to move
    def dest(self, oid: str) -> dict | None:
        for a in self.atoms:
            if a["pred"] in ("on", "in", "held_by") and a["args"][0] == oid:
                return a
        return None

    def objects(self) -> list[str]:
        return [a["args"][0] for a in self.atoms if a["pred"] in ("on", "in", "held_by")]

    def dest_text(self, a: dict, L: str) -> str:
        if a["pred"] in ("on", "in"):
            return _say(a["pred"], L, place=place_name(self.w, a["args"][1], L))
        if a["args"][1] == self.user_id:
            return _say("to_me", L)
        return _say("to_person", L, person=person_name(self.w, a["args"][1], L))

    def fix_text(self, a: dict, L: str) -> str:
        p, args = a["pred"], a["args"]
        if p in ("on", "in", "held_by"):
            obj = _specific_name(self.w, args[0], L)
            if p in ("on", "in"):
                return _say("fix_" + p, L, obj=obj, place=place_name(self.w, args[1], L))
            if args[1] == self.user_id:
                return _say("fix_to_me", L, obj=obj)
            return _say("fix_to_person", L, obj=obj, person=person_name(self.w, args[1], L))
        if p in ("open", "closed"):
            return _say("fix_open" if p == "open" else "fix_close", L, place=place_name(self.w, args[0], L))
        if p == "robot_at_any":
            return _say("fix_go", L, place=place_name(self.w, args[0], L))
        if p == "robot_at":
            return _say("fix_go", L, place=place_name(self.w, args[0], L))
        if p == "docked":
            return _say("fix_dock", L)
        if p == "said_to":
            return _say("fix_say", L, person=person_name(self.w, args[0], L))
        return GOAL_TEXT["no"][L]

    def subject_said(self, a: dict, q: str) -> bool:
        """Does the question name what the atom is about (its object / container / person / place)?"""
        p, args = a["pred"], a["args"]
        if p in ("on", "in", "held_by"):
            return _mentions_any(q, _obj_words(self.w, args[0]))
        if p in ("open", "closed", "robot_at"):
            return _mentions_any(q, _place_words(self.w, args[0]))
        if p == "robot_at_any":
            return any(_mentions_any(q, _place_words(self.w, x)) for x in args)
        if p == "docked":
            return any(k in q.lower() for k in DOCK_WORDS)
        if p == "said_to":
            return _mentions_any(q, _person_words(self.w, args[0]))
        return False

    def covered(self, a: dict, q: str) -> bool:
        """Does the question (a read-back of the plan) state this atom the way the user asked for it?"""
        p, args = a["pred"], a["args"]
        if p in ("on", "in"):
            return self.subject_said(a, q) and _mentions_any(q, _place_words(self.w, args[1]))
        if p == "held_by":
            if not self.subject_said(a, q):
                return False
            if args[1] == self.user_id:
                here = self.place_of(args[1])
                return bool(ME_RX["en"].search(q.lower()) or ME_RX["ko"].search(q)
                            or (here and _mentions_any(q, _place_words(self.w, here))))
            return self._person_ok(args[1], q)
        if p == "said_to":
            return self._person_ok(args[0], q)
        return self.subject_said(a, q)

    def _person_ok(self, pid: str, q: str) -> bool:
        """The person is named, or their place is; a place named for them must be where they are."""
        here = self.place_of(pid)
        at_here = bool(here and _mentions_any(q, _place_words(self.w, here)))
        named = _mentions_any(q, _person_words(self.w, pid))
        other_place = any(_mentions_any(q, _place_words(self.w, k)[:2]) for k in sorted(self.w.house.places)
                          if k != here)
        return at_here or (named and not other_place)


def compose_from_goal(question: str, L: str, world: Any, gv: GoalView, *, knows_location: bool,
                      other_place: str | None = None) -> Content | None:
    """Answer content from what the user asked for, or None when no rule applies (see the section comment)."""
    if not gv.atoms:
        return None
    q = _q_text(question)
    qtype = classify(question)
    low = q.lower()
    goal_objs = [o for o in dict.fromkeys(gv.objects()) if _mentions_any(q, _obj_words(world, o))]
    alt = bool(ALT_RX.search(low))
    wrong_place = None
    if other_place is not None:
        key = "in" if getattr(world.house.places.get(other_place), "kind", "") == "container" else "on"
        wrong_place = _say(key, L, place=place_name(world, other_place, L))

    # 1. "Where should I put / bring the X?": where the user wants it
    is_dest = asks_destination(question)
    if not goal_objs and is_dest:
        # "어디에 가져다줘야 할까요?" (Korean drops the object) / "Where should I put it?": the one thing asked for
        movers = [o for o in dict.fromkeys(gv.objects())]
        dests = {gv.dest_text(gv.dest(o), L) for o in movers}
        pron = L == "ko" or bool(re.search(r"\b(it|them|this|that)\b", low))
        if pron and movers and len(dests) == 1:
            return Content("correct", dests.pop(), True, wrong_place, "goal_destination")
    if goal_objs and is_dest:
        parts = []
        if (LOC_RX["en"].search(low) or LOC_RX["ko"].search(q)) and knows_location:
            # "where is it, and where should it go?"
            if len(goal_objs) == 1:
                parts.append(location_text(world, goal_objs[0], L))
            else:
                parts += [(f"The {_specific_name(world, o, L)}: " if L == "en" else f"{_specific_name(world, o, L)}: ")
                          + location_text(world, o, L) for o in goal_objs[:2]]
        parts.append(_dest_answer(gv, goal_objs, L))
        return Content("correct", " ".join(parts), True, wrong_place, "goal_destination")

    # 2. "Which one: the red book or the blue book?": the object the user asked for
    specific = [o for o in sorted(world.objects)
                if any(mentions(q, n, lg) for lg in ("en", "ko") for n in object_names(world, o, lg)[:1])]
    if (qtype == "wh" or alt) and len(goal_objs) == 1 and len(specific) >= 2 and goal_objs[0] in specific:
        other = next(o for o in specific if o != goal_objs[0])
        return Content("correct", _say("pick", L, name=_specific_name(world, goal_objs[0], L)), True,
                       _say("pick", L, name=_specific_name(world, other, L)), "goal_object")
    # "Did you mean the blue book?" when the user asked for the red one: "No, the red book."
    cls_of = lambda o: getattr(world.objects[o], "cls", None)  # noqa: E731
    wrong_kin = [o for o in specific if o not in gv.objects() and any(cls_of(o) == cls_of(g) for g in goal_objs)]
    if wrong_kin and not any(g in specific for g in goal_objs):
        mine = next(g for g in goal_objs if cls_of(g) == cls_of(wrong_kin[0]))
        name = _say("pick", L, name=_specific_name(world, mine, L))
        if qtype == "yes_no" and not alt:
            return Content("no", GOAL_TEXT["no"][L][:-1] + ", " + name[:1].lower() + name[1:] if L == "en"
                           else "아니요, " + name, True, _say("yes", L), "goal_object")
        return Content("correct", name, True, _say("pick", L, name=_specific_name(world, wrong_kin[0], L)),
                       "goal_object")

    # 2b. "Should I put the X on A or on B?" / "bring it to you or put it somewhere?": where it goes
    about_where = bool(re.search(r"\b(put|place|bring|take|leave|move|give|hand|somewhere|where|to you)\b", low)
                       or re.search(r"(두|놓|놔|넣|가져|갖다|어디|드릴)", q)
                       or any(_mentions_any(q, _place_words(world, k)[:2]) for k in sorted(world.house.places)))
    if goal_objs and alt and about_where and qtype in ("wh", "yes_no") and not READBACK_RX.search(q):
        return Content("correct", _dest_answer(gv, goal_objs, L), True, wrong_place, "goal_destination")

    # 3. "Which place do you mean: A or B or C?": the place the request names
    places = [pid for pid in sorted(world.house.places) if _mentions_any(q, _place_words(world, pid)[:2])]
    if (qtype == "wh" or alt) and len(places) >= 2:
        targets = []
        for a in gv.atoms:
            if a["pred"] in ("on", "in"):
                targets.append(a["args"][1])
            elif a["pred"] in ("open", "closed", "robot_at"):
                targets.append(a["args"][0])
            elif a["pred"] == "robot_at_any":
                targets += list(a["args"])
            elif a["pred"] in ("said_to", "held_by"):
                person = a["args"][0] if a["pred"] == "said_to" else a["args"][1]
                if person != gv.user_id:
                    targets.append(gv.place_of(person))
        hits = [p for p in places if p in targets]
        if not hits:
            # none of the offered places is where the request goes: the person it is for, or "to me"
            for a in gv.atoms:
                if a["pred"] in ("held_by", "said_to"):
                    person = a["args"][1] if a["pred"] == "held_by" else a["args"][0]
                    if person == gv.user_id:
                        return Content("correct", _say("to_me", L), True, None, "goal_place")
                    here = gv.place_of(person)
                    if here:
                        txt = _say("person_at", L, person=person_name(world, person, L), place=place_name(world, here, L))
                        return Content("correct", txt[:1].upper() + txt[1:], True, None, "goal_place")
        if hits:
            others = [p for p in places if p not in targets]
            return Content("correct", _say("pick", L, name=place_name(world, hits[0], L)), True,
                           _say("pick", L, name=place_name(world, others[0], L)) if others else None, "goal_place")

    # 4. "Where is <person>?": where that person is now (a household member knows, unless they do not)
    if qtype == "wh" and (LOC_RX["en"].search(low) or LOC_RX["ko"].search(q) or "where" in low or "어디" in q):
        for pid in sorted(world.people):
            if pid != gv.user_id and _mentions_any(q, _person_words(world, pid)):
                if not knows_location:
                    return Content("not_sure", TEXT["dont_know"][L], False, None, "location_unknown")
                here = gv.place_of(pid)
                if here:
                    txt = _say("person_at", L, person=person_name(world, pid, L), place=place_name(world, here, L))
                    return Content("correct", txt[:1].upper() + txt[1:], True, None, "person_location")

    # 5. yes / no: a read-back of the whole plan, or a question about one part of the request
    if qtype == "yes_no":
        readback = bool(READBACK_RX.search(q))
        rel = gv.atoms if readback else [a for a in gv.atoms if gv.subject_said(a, q)]
        if rel:
            bad = [a for a in rel if not gv.covered(a, q)]
            if not bad:
                return Content("yes", _say("yes", L), True, _say("no", L), "goal_confirm")
            return Content("no", gv.fix_text(bad[0], L), True, _say("yes", L), "goal_correct")
    return None
