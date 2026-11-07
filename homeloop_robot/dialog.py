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
# plain Korean "어디(에) 있어요?" with no object / person / place named: asked of the listener, "where are you?"
SELF_WHERE_KO_PLAIN = re.compile(r"(지금\s*)?어디\s*(에)?\s*있(어요|어|으세요|나요|니|습니까)\s*\??")
# what may come before that plain "어디 있어요?" for it to be asked of the listener: an apology, an opener or 지금 /
# 혹시 / 그럼. Anything else is a subject ("그거 어디 있어요?", "말씀하신 물건은 ...", "찾으시는 게 ..."): the question is
# about that thing, not about the listener
KO_WHERE_LEAD = re.compile(r"^(?:\s|[,.!~]|죄송한데요?|죄송하지만|죄송해요|실례지만|저기요?|근데|그런데|"
                           r"지금|혹시|그럼|그러면|네|아)*$")

# ASR repair (R2-5 B3, docs/user_model.md): "Did you mean X?" about the user's own words, and "could you repeat?"
MEAN_RX = {"en": re.compile(r"\b(did|do) you (mean|say|want)\b|\bby\b.+\bdo you mean\b|\bwas it\b|\btypo\b"),
           "ko": re.compile(r"말씀(이세요|이신가요|이시죠|하신\s*(거|건)|하셨)|(이)?라고\s*(하셨|하신|말씀)|"
                            r"(인가요|인지요|맞나요|맞아요|맞죠)\s*\??$|오타")}
QUOTE_RX = re.compile(r"[\'\"‘’“”「」『』]([^\'\"‘’“”「」『』]{2,80})[\'\"‘’“”「」『』]")
REPEAT_RX = {"en": re.compile(r"\b(repeat|say (that|it) again|come again|pardon|what did you (say|ask)|"
                              r"one more time|didn'?t (catch|hear|get) (that|it|you|what you said))\b"),
             "ko": re.compile(r"다시\s*(한\s*번\s*)?(말씀|말해|얘기|이야기)|뭐라고\s*(하셨|했|하신)|"
                              r"한\s*번\s*더\s*(말씀|말해)|잘\s*못\s*들었")}
# a repeat request that names the request itself ("what you'd like me to do", "부탁하신 거")
REQUEST_REF_RX = {"en": re.compile(r"\b(what you( want| would like|'d like| asked| said| need)|your (request|task|"
                                   r"instruction)|the (request|task|instruction)|what i should do)\b"),
                  "ko": re.compile(r"부탁|요청|시키신|원하시|해\s*달라")}


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
    # a quote mark is not part of a word ("'sink'" names the sink); an apostrophe inside one is ("you're")
    t = re.sub(r"(?<!\w)'|'(?!\w)", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if lang == "ko":
        t = t.replace(" ", "")
    return t


def _spans(q: str, m: str, lang: str) -> list[tuple[int, int]]:
    """Where normalised phrase ``m`` occurs in normalised text ``q``: any position in Korean (spaces are removed,
    particles attach), on word boundaries in English. Positions are in ``q`` padded with one space each side."""
    hay, needle = (f" {q} ", m) if lang == "ko" else (f" {q} ", f" {m} ")
    out, i = [], hay.find(needle)
    while i >= 0:
        out.append((i, i + len(needle)))
        i = hay.find(needle, i + 1)
    return out


def ko_plural_forms(phrase: str) -> list[str]:
    """A Korean name of several words and its forms with the plural marker 들 on a word before the head noun: '아이
    책상' -> ['아이 책상', '아이들 책상'] ("the kids' desk"; 들 attaches to a noun, fresh pilot round 2,
    hl-dev-000057 KO: '아이들 책상' was read as the study desk). One word, or an English name: the name itself."""
    words = str(phrase or "").split()
    if detect_lang(str(phrase or "")) != "ko" or len(words) < 2:
        return [phrase]
    out = [phrase]
    for i, w in enumerate(words[:-1]):
        if _hangul_word(w) and not w.endswith("들"):
            out.append(" ".join(words[:i] + [w + "들"] + words[i + 1:]))
    return out


def _hangul_word(w: str) -> bool:
    return bool(w) and all("가" <= ch <= "힣" for ch in w)


def mentions(text: str, phrase: str, lang: str, world: Any = None) -> bool:
    """Does ``text`` name ``phrase``? With ``world``, longest match (R2-6 H2): an occurrence inside a longer name
    of a DIFFERENT thing of the world, one that is not itself also called ``phrase``, does not count. 냉장고 in
    김치냉장고 and "fridge" in "kimchi fridge" name the kimchi fridge, not the fridge; "cup" in "red cup" still
    names a cup (the red cup is called "cup" too). A Korean name is also named with the plural marker 들 on a word
    before its head ('아이들 책상' names '아이 책상', :func:`ko_plural_forms`)."""
    q, m = normalize(text, lang), normalize(phrase, lang)
    if not m:
        return False
    if lang == "ko":
        forms = [f for f in dict.fromkeys(normalize(x, lang) for x in ko_plural_forms(phrase)) if f]
        if len(forms) > 1:
            return any(_mentions_norm(q, f, lang, world) for f in forms)
    return _mentions_norm(q, m, lang, world)


def _mentions_norm(q: str, m: str, lang: str, world: Any = None) -> bool:
    spans = _spans(q, m, lang)
    if not spans or world is None:
        return bool(spans)
    longer = [(sp, names) for n, names in _compound_names(world, lang) if len(n) > len(m) and m in n
              and m not in names for sp in _spans(q, n, lang)]
    if not longer:
        return True
    return any(not any(a <= s and e <= b for (a, b), _ in longer) for s, e in spans)


def _compound_names(world: Any, lang: str) -> list[tuple[str, frozenset]]:
    """(normalised name, normalised names of the same thing) for every object, place and person of ``world``
    in ``lang``; cached on the world (names do not change during an episode)."""
    cache = getattr(world, "_hl_names_cache", None)
    if cache is None:
        cache = {}
        try:
            world._hl_names_cache = cache
        except AttributeError:                    # a world that takes no attributes: no cache
            pass
    if lang in cache:
        return cache[lang]
    groups = [_obj_words(world, o) for o in sorted(getattr(world, "objects", {}) or {})]
    groups += [_place_words(world, p) for p in sorted(world.house.places)] if getattr(world, "house", None) else []
    groups += [_person_words(world, p) for p in sorted(getattr(world, "people", {}) or {})]
    out = []
    for g in groups:
        names = frozenset(normalize(f, lang) for x in g if x and detect_lang(x) == lang for f in ko_plural_forms(x))
        out += [(n, names) for n in sorted(names) if n]
    cache[lang] = out
    return out


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
    """Object ids the question names, by their most specific name (both languages): an object named only where a
    longer name of another object is named ("book" inside "red book") is left out, so "the red book or the book?"
    keeps the red one only when nothing else is named, while "the reading glasses and the remote" names both (the
    earlier rule kept only the objects with the longest name anywhere in the question: the remote was dropped,
    fresh pilot round 1, hl-dev-000016)."""
    found: dict[str, list] = {}
    for oid in sorted(world.objects):
        for lang in ("en", "ko"):
            q = normalize(question, lang)
            for n in object_names(world, oid, lang):
                if mentions(question, n, lang, world):
                    m = normalize(n, lang)
                    found.setdefault(oid, []).extend((lang, a, b, len(m)) for a, b in _spans(q, m, lang))
    if not found:
        return []
    out = []
    for o, spans in found.items():
        others = [x for p, sp in found.items() if p != o for x in sp]
        if any(not any(lg2 == lg and n2 > n and a2 <= a and b <= b2 for lg2, a2, b2, n2 in others)
               for lg, a, b, n in spans):
            out.append(o)
    return sorted(out)


def clear_place_name(world: Any, pid: str, lang: str) -> str:
    """The place's name, with its room when the name alone is the end of another place's name in the house ("desk"
    and "kid's desk": "the desk in the study"), as a person says where something is when "the desk" could be heard
    as either (fresh pilot round 1, hl-dev-000016: "It's on the desk." then "Which desk do you mean?")."""
    name = place_name(world, pid, lang)
    pl = world.house.places.get(pid)
    if pl is None or not name:
        return name
    n = normalize(name, lang)
    for k, other in world.house.places.items():
        o = normalize(place_name(world, k, lang), lang)
        if k != pid and o != n and (o.endswith(" " + n) if lang == "en" else o.endswith(n)):
            room = world.house.rooms.get(pl.room)
            rname = (room.name.get(lang) or room.name.get("en", "")) if room is not None else ""
            if not rname or normalize(rname, lang) in n:
                return name
            return f"{name} in the {rname}" if lang == "en" else f"{rname} {name}"
    return name


def location_text(world: Any, oid: str, lang: str, at: str | None = None) -> str:
    """Where object ``oid`` is ("It's on the desk in the study."); ``at``: another place to name instead."""
    at = at or world.objects[oid].at
    if at == "robot":
        return TEXT["robot"][lang]
    if at.startswith("person:"):
        return TEXT["person"][lang].format(person=person_name(world, at.split(":", 1)[1], lang))
    key = "in" if getattr(world.objects[oid], "inside", False) else "on"
    pl = world.house.places.get(at)
    if pl is not None and at != world.objects[oid].at:
        key = "in" if getattr(pl, "kind", "") == "container" else "on"
    return TEXT[key][lang].format(place=clear_place_name(world, at, lang))


LOC_NAMED = {"on": {"en": "The {obj} is on the {place}.", "ko": "{obj}{eun} {place} 위에 있어요."},
             "in": {"en": "The {obj} is in the {place}.", "ko": "{obj}{eun} {place} 안에 있어요."},
             "robot": {"en": "You are holding the {obj}.", "ko": "{obj}{eun} 지금 들고 있잖아요."},
             "person": {"en": "{person} has the {obj}.", "ko": "{obj}{eun} {person}한테 있어요."}}


def locations_text(world: Any, objs: list, lang: str, wrong_at: str | None = None) -> str:
    """Where each of several objects is, each named ("The black glasses are on the desk in the study. The black
    remote control is on the sofa."): a "where are X and Y?" answered for both (fresh pilot round 1,
    hl-dev-000016). ``wrong_at``: a mistaken place for the first one (the wrong-answer draw)."""
    if len(objs) == 1:
        return location_text(world, objs[0], lang, wrong_at)
    out = []
    for i, o in enumerate(objs):
        at = (wrong_at if i == 0 and wrong_at else None) or world.objects[o].at
        name = _specific_name(world, o, lang)
        if at == "robot":
            key, kw = "robot", {}
        elif at.startswith("person:"):
            key, kw = "person", {"person": person_name(world, at.split(":", 1)[1], lang)}
        else:
            pl = world.house.places.get(at)
            inside = (getattr(pl, "kind", "") == "container") if at != world.objects[o].at else \
                bool(getattr(world.objects[o], "inside", False))
            key, kw = ("in" if inside else "on"), {"place": clear_place_name(world, at, lang)}
        fmt = LOC_NAMED[key][lang]
        if lang == "ko":
            t = _ko(fmt, obj=name, **kw)
        else:
            t = fmt.format(obj=name, **kw)
            if name.endswith("s") and not name.endswith("ss") and key in ("on", "in"):
                t = t.replace(" is ", " are ", 1)      # "the glasses are", "the keys are"
        out.append(t[:1].upper() + t[1:])
    return " ".join(out)


def asks_user_position(question: str, world: Any = None) -> bool:
    """Does the question ask where the user is ("Where are you?", "지금 어디에 계세요?")? With ``world``, a plain
    Korean "어디(에) 있어요?" that names no object, person or place counts as well (said to the listener)."""
    q = unicodedata.normalize("NFC", str(question or "")).lower()
    if any(re.search(rx, q) for lg in ("en", "ko") for rx in SELF_WHERE[lg]):
        return True
    if world is None:
        return False
    for seg in re.split(r"(?<=[?.!])\s*", q):
        m = SELF_WHERE_KO_PLAIN.search(seg)
        if m and KO_WHERE_LEAD.match(seg[:m.start()]) and not _names_anything(world, seg):
            return True
    return False


def _names_anything(world: Any, text: str) -> bool:
    """Does ``text`` name an object, a place or a person of the world (any language)?"""
    if mentioned_objects(world, text):
        return True
    for pid in sorted(world.house.places):
        if _mentions_any(_q_text(text), _place_words(world, pid), world):
            return True
    return any(_mentions_any(text, _person_words(world, pid), world) for pid in sorted(world.people))


def _strip_det(x: str, L: str) -> str:
    x = x.strip().strip("?.!,")
    if L == "en":
        x = re.sub(r"^(the|a|an|my|your|that|this)\s+", "", x.lower())
    return x.strip()


def mean_phrases(question: str, L: str) -> list[str]:
    """The phrases X of a "did you mean X?" repair question: quoted phrases, else the words after "mean" /
    before "말씀" (one phrase)."""
    q = unicodedata.normalize("NFC", str(question or ""))
    quoted = [m.group(1).strip() for m in QUOTE_RX.finditer(q)]
    if quoted:
        return quoted
    if L == "en":
        m = re.search(r"\b(?:did|do) you (?:mean|say|want)\s+(.+?)(?:\?|$|,|\bor\b)", q, re.I)
        return [m.group(1).strip()] if m else []
    m = re.search(r"(.+?)\s*(?:(?:이)?라고\s*(?:하셨|하신|말씀)|말씀(?:이세요|이신가요|이시죠|하신|하셨)|"
                  r"(?:인가요|맞나요|맞아요|맞죠))", q)
    return [m.group(1).strip().split("?")[-1].strip()] if m else []


def own_phrase(world: Any, x: str, L: str, request: str | None, goal: "GoalView | None") -> bool:
    """Is X a word of the user's own request, or the name of something their request is about?"""
    x0 = _strip_det(x, L)
    nx = normalize(x0, L)
    if len(nx.replace(" ", "")) < 2:
        return False
    if request and nx in normalize(request, L):
        return True
    if goal is not None:
        ents = set(goal.objects())
        names = [n for o in ents if o in world.objects for n in object_names(world, o, L)]
        for a in goal.atoms:
            for arg in a.get("args") or []:
                if arg in world.house.places:
                    names += _place_words(world, arg)
                elif arg in world.people:
                    names += _person_words(world, arg)
        if any(normalize(n, L) == nx for n in names if n):
            return True
    return False


def is_repeat_request(question: str) -> bool:
    q = unicodedata.normalize("NFC", str(question or ""))
    return bool(REPEAT_RX["en"].search(q.lower()) or REPEAT_RX["ko"].search(q))


def names_request(question: str) -> bool:
    q = unicodedata.normalize("NFC", str(question or ""))
    return bool(REQUEST_REF_RX["en"].search(q.lower()) or REQUEST_REF_RX["ko"].search(q))


def repair(question: str, L: str, world: Any, *, request: str | None, last_answer: str | None,
           goal: "GoalView | None", spec: dict | None = None) -> Content | None:
    """ASR repair questions about the user's own words (R2-5 B3), or None.

    * "could you repeat?" / "다시 말씀해 주시겠어요?": the user says it again. Right after the request (or when the
      question names the request) that is the original request text; after an answer of theirs, that answer.
      ASR applies again (user.answer); a person does not get their own words wrong, so it is not informative.
    * "Did you mean X?" where X is a word of the request or names something the request is about: "yes", and
      the user restates the request (informative: the wrong / not-sure mix applies; a wrong draw is "not sure").
    """
    if not request:
        return None
    if is_repeat_request(question):
        if last_answer and not names_request(question):
            return Content("correct", last_answer, False, None, "repeat_answer")
        return Content("correct", request, False, None, "repeat_request")
    q = unicodedata.normalize("NFC", str(question or ""))
    if MEAN_RX["en"].search(q.lower()) or MEAN_RX["ko"].search(q):
        # a read-back of a message to pass on ('남편이 “...”라고 말할 거예요, 맞죠?', "I'll tell grandpa '...', right?")
        # quotes the user's words as the message, not as a word the robot heard: the goal rules judge it (who is
        # told what), pilot round 2 hl-dev-000013 KO
        if message_readback(world, q, goal):
            return None
        xs = mean_phrases(q, L)
        # a word of the user's own LAST ANSWER is theirs too ("Did you mean 'wardrobe'?" after "it is in the
        # wardrobe"): the user confirms it and says that answer again, not the request
        said = request
        if xs and not any(own_phrase(world, x, L, request, goal) for x in xs) and last_answer \
                and any(own_phrase(world, x, L, last_answer, goal) for x in xs):
            said = last_answer
        if not xs or not any(own_phrase(world, x, L, said, goal) for x in xs):
            return None
        # "Did you mean 'sink' or 'kimchi fridge'?" is a choice, not a check of what was heard: the user picks
        if _either_or(q):
            return None
        # a question that names something the request is not about ("Did you mean 'mug', the red coffee mug?" when
        # the blue one is wanted, "'sink' or ...") is answered about that thing (clarification / goal), never "yes"
        if _names_foreign(world, q, L, request + (" " + last_answer if said != request else ""), goal, spec):
            return None
        yes = {"en": "Yes. ", "ko": "네. "}[L]
        return Content("yes", yes + said, True, None, "repair_confirm")
    return None


MESSAGE_READBACK_RX = {
    "en": re.compile(r"\b(?:i will|i'll|i'm going to|i am going to|will|is going to)\s+(?:say|tell|let|pass)\b|"
                     r"\b(?:says|is saying|is the one saying)\b"),
    "ko": re.compile(r"(?:말할|말하는|말해\s*줄|전할|전하는|전해\s*줄|전해\s*드릴|말씀\s*드릴|알려\s*줄|알려\s*드릴)\s*"
                     r"(?:거|것|게|겁)")}


def message_readback(world: Any, q: str, goal: "GoalView | None") -> bool:
    """Does ``q`` read back a message of the request: it says someone will say something, or names a person the
    message goes to in a role (listener / speaker, :func:`speech_role`)?"""
    if goal is None or not any(a["pred"] == "said_to" for a in goal.atoms):
        return False
    t = QUOTED_RX.sub(" ", unicodedata.normalize("NFC", str(q or "")))
    if MESSAGE_READBACK_RX["en"].search(t.lower()) or MESSAGE_READBACK_RX["ko"].search(t):
        return True
    return any(speech_role(world, a["args"][0], q) for a in goal.atoms if a["pred"] == "said_to")


PLAN_READBACK_RX = {
    "en": re.compile(r"\b(?:i will|i'll|i am going to|i'm going to)\b.*\b(?:is that (?:right|correct)|right|correct)\s*\?\s*$",
                     re.I | re.S),
    "ko": re.compile(r"(?:게요|겠어요|겠습니다|할 거예요|할게요|ㄹ게요)[.!\s]*(?:맞아요|맞나요|맞죠|맞습니까|맞을까요)\s*\?\s*$")}


def extra_message(q: str, goal: "GoalView | None") -> bool:
    """Does the read-back ``q`` say something is to be said or told while the request holds no message?"""
    if goal is None or any(a["pred"] == "said_to" for a in goal.atoms):
        return False
    t = QUOTED_RX.sub(" ", unicodedata.normalize("NFC", str(q or "")))
    return bool(MESSAGE_READBACK_RX["en"].search(t.lower()) or MESSAGE_READBACK_RX["ko"].search(t)
                or EXTRA_MESSAGE_RX["en"].search(t.lower()) or EXTRA_MESSAGE_RX["ko"].search(t))


EXTRA_MESSAGE_RX = {"en": re.compile(r"\b(?:say|tell|pass on|let \w+ know)\b"),
                    "ko": re.compile(r"(?:말\s*(?:할|해|씀)|전\s*(?:할|해)|알려)")}


def is_plan_readback(question: str) -> bool:
    """Is ``question`` the robot reading back what it will do and asking if that is right (not a question
    about a refusal)?"""
    q = unicodedata.normalize("NFC", str(question or ""))
    return bool(PLAN_READBACK_RX["en"].search(q) or PLAN_READBACK_RX["ko"].search(q))


def plan_readback_answer(question: str, L: str, world: Any, request: str | None, *, structured: bool = False) -> "Content | None":
    """The answer to a plan read-back when the task scripts no goal view (a refused request): the user said what
    they want, so the read-back that names every object of the request is right ("Yes, that's right."); one
    that leaves an object of the request out (a model that heard another word) is wrong and the user says the
    request again. None when ``question`` is no read-back or the request is not known."""
    if not request or not (structured or is_plan_readback(question)):
        return None
    want = set(mentioned_objects(world, request))
    if not want or want <= set(mentioned_objects(world, question)):
        return Content("yes", TEXT_GOAL_YES[L], True, None, "plan_readback")
    return Content("no", TEXT_GOAL_NO[L] + " " + request, True, None, "plan_readback")


TEXT_GOAL_YES = {"en": "Yes, that's right.", "ko": "네, 맞아요."}
TEXT_GOAL_NO = {"en": "No.", "ko": "아니요."}


def _either_or(q: str) -> bool:
    """Two quoted phrases joined by "or" / 아니면 in one sentence ("Did you mean 'A' or 'B'?"). "Did you mean 'A'? Or
    was 'B' a typo?" (two sentences: a check of a misheard word) is not."""
    for seg in re.split(r"(?<=[?.!])\s*", q):
        spans = [m.span() for m in QUOTE_RX.finditer(seg)]
        for (_, e1), (s2, _) in zip(spans, spans[1:]):
            if ALT_RX.search(seg[e1:s2].lower()):
                return True
    return False


def _names_foreign(world: Any, q: str, L: str, request: str, goal: "GoalView | None", spec: dict | None) -> bool:
    """Does the question name an object, place, person or task candidate that the user's request is not about?
    A name counts as the request's own when its entity is in the goal or the name itself is a word of the request
    ("mug" in "Put the mug on the nightstand" is; "red coffee mug" is not when the red mug is not wanted)."""
    nreq = normalize(request, L)
    goal_ids: set[str] = set()
    if goal is not None:
        goal_ids |= set(goal.objects())
        for a in goal.atoms:
            goal_ids |= {x for x in (a.get("args") or []) if isinstance(x, str)}
        if goal.user_id:
            goal_ids.add(goal.user_id)
    intended = (spec or {}).get("intended")
    if intended:
        goal_ids.add(intended)
    qt = _q_text(q)

    def foreign(names) -> bool:
        for n in names:
            lg = detect_lang(n)
            if n and mentions(qt, n, lg, world) and not (lg == L and normalize(n, L) in nreq):
                return True
        return False

    for oid in sorted(world.objects):
        if oid not in goal_ids and foreign(_obj_words(world, oid)):
            return True
    for pid in sorted(world.house.places):
        if pid not in goal_ids and foreign(_place_words(world, pid)):
            return True
    for pid in sorted(world.people):
        if pid not in goal_ids and foreign(_person_words(world, pid)):
            return True
    for c in (spec or {}).get("candidates") or []:
        if c.get("id") != intended and foreign([m for lg in ("en", "ko") for m in (c.get("mentions") or {}).get(lg, [])]):
            return True
    return False


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
            goal: "GoalView | None" = None, request: str | None = None,
            last_answer: str | None = None) -> Content:
    """Answer content for ``question`` (DESIGN 5.2 rules 3-4), before the correctness mix.

    ``knows_location``: whether the user knows where an asked-about object is (drawn by the caller);
    ``other_place``: a place id used for a wrong location answer;
    ``user_place``: ``(place_id, moving)`` of the answering user, for "where are you?";
    ``goal``: what the user asked for (:class:`GoalView`), for questions about the request itself
    (:func:`compose_from_goal`); None = those questions are not understood;
    ``request`` / ``last_answer``: the user's own request text and their last answer, for ASR repair
    questions (:func:`repair`); None = not known.
    """
    qtype = classify(question)
    L = answer_lang
    spec = spec or {}
    cands = spec.get("candidates") or []
    ans = spec.get("answer")

    def in_any_lang(phrases: dict) -> bool:
        return any(mentions(question, p, lg, world) for lg in ("en", "ko") for p in (phrases or {}).get(lg, []))

    # "where are you?" (naming no candidate): the user says where they are (or where they are walking to); people
    # do not get their own position wrong, so the answer is not informative in the correctness-mix sense (ASR
    # still applies)
    if request and is_repeat_request(question):
        c = repair(question, L, world, request=request, last_answer=last_answer, goal=goal)
        if c is not None:
            return c
    if user_place is not None and qtype == "wh" and asks_user_position(question, world) and \
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
        # "A or B?" naming one candidate and something else is a choice, not a yes / no question
        either = bool(hit) and _either_or(_q_text(question))
        if qtype == "yes_no" and len(hit) == 1 and not either:
            if hit[0].get("id") == intended:
                return Content("yes", TEXT["yes"][L], True,
                               TEXT["no"][L] + lower_first(wrong) if wrong else None, "yes_no_intended")
            return Content("no", TEXT["no"][L] + lower_first(ans[L]), True, TEXT["yes"][L], "yes_no_other")
        if qtype == "wh" or len(hit) >= 2 or either:
            return Content("correct", ans[L], True, wrong, "clarify_answer")
    # a read-back of the plan is answered about the plan, not with the script for a refusal (the user asked for
    # it; "Oh, right. Never mind." answers an explanation)
    if ans and not cands and goal is None:
        c = plan_readback_answer(question, L, world, request)
        if c is not None:
            return c
    # a resolution the task scripts (safety clarification, confirmation of a refused request)
    if ans and not cands and qtype in ("wh", "yes_no"):
        wt = spec.get("wrong_answer")
        return Content("correct", ans[L], True, wt[L] if isinstance(wt, dict) else None, "scripted_answer")
    # "Did you mean X?" about the user's own words (ASR repair)
    if request:
        c = repair(question, L, world, request=request, last_answer=last_answer, goal=goal, spec=spec)
        if c is not None:
            return c
    # a question about the request itself: where an object goes, which one / which place, a read-back
    if goal is not None:
        c = compose_from_goal(question, L, world, goal, knows_location=knows_location, other_place=other_place,
                              request=request)
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
        asked = [o for o in objs if goal is not None and o in goal.objects()]
        if len(objs) > 1 and len(asked) >= 2:
            # "where are the glasses and the remote?": where each one is
            if not knows_location:
                return Content("not_sure", TEXT["dont_know"][L], False, None, "location_unknown")
            return Content("correct", locations_text(world, asked[:3], L), True,
                           locations_text(world, asked[:3], L, other_place) if other_place else None, "location")
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
    "just_open": {"en": "Please don't move it, just open the {place}.", "ko": "옮기지 말고 {place}{eul} 열어만 주세요."},
    "just_close": {"en": "Please don't move it, just close the {place}.", "ko": "옮기지 말고 {place}{eul} 닫아만 주세요."},
    "fix_close": {"en": "No, close the {place}.", "ko": "아니요, {place}{eul} 닫아 주세요."},
    "fix_go": {"en": "No, go to the {place}.", "ko": "아니요, {place}{ro} 가 주세요."},
    "fix_dock": {"en": "No, go back to the charger.", "ko": "아니요, 충전기로 돌아가 주세요."},
    "fix_say": {"en": "No, I asked you to tell {person}.", "ko": "아니요, {person}한테 말해 달라고 했어요."},
    "fix_say_msg": {"en": "No, tell {person}: {msg}", "ko": "아니요, {person}한테 \"{msg}\"라고 말해 주세요."},
    "msg_not_place": {"en": "None of those. Please just tell {person}: {msg}",
                      "ko": "그런 곳은 아니에요. {person}한테 \"{msg}\"라고 말해 주세요."},
    "person_at": {"en": "{person} is at the {place}.", "ko": "{person}{eun} {place}에 있어요."},
    "anywhere_in": {"en": "Anywhere in the {room} is fine.", "ko": "{room} 안이면 아무 데나 괜찮아요."},
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
# (the speaker's ENV key "spot within your reach" is read back as "on the spot within your reach"; in Korean "손이 닿는
# 곳 / 손 닿는 자리")
ME_RX = {"en": re.compile(r"\b(you|your hand|your reach|to me|hand it|give it)\b"),
         "ko": re.compile(r"(드리|드릴|드려|갖다\s*드|가져다\s*드|건네|손에|당신|손이?\s*닿는)")}
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


def _mentions_any(q: str, phrases, world: Any = None) -> bool:
    return any(mentions(q, p, lg, world) for p in phrases for lg in ("en", "ko") if detect_lang(p) == lg)


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
            # what the user says about a delivery ("bring it to me") does not depend on reach / hand; the mode is
            # kept: a person who asked for something to be brought (reach) takes "on the side table beside you" for
            # it, one who asked for it in the hand does not (:meth:`GoalView._put_down_for`)
            a = {"pred": "held_by", "args": list(a.get("args") or []), "mode": a.get("mode")}
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

    def fix_text(self, a: dict, L: str, q: str | None = None) -> str:
        """The correction of atom ``a`` the read-back ``q`` got wrong."""
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
            if q is not None and self._person_ok(args[0], q) and speech_role(self.w, args[0], q) != "speaker":
                # the right person, the wrong message: the user corrects what is to be said (fresh pilot round 1,
                # hl-dev-000057: "No, I asked you to tell the kid." when the kid was named)
                from homeloop_robot.catalog import MESSAGE_TEXT  # robot core
                msg = (MESSAGE_TEXT.get(args[1]) or {}).get(L)
                if msg:
                    return _say("fix_say_msg", L, person=person_name(self.w, args[0], L),
                                msg=msg.rstrip(".") if L == "ko" else msg)
            return _say("fix_say", L, person=person_name(self.w, args[0], L))
        return GOAL_TEXT["no"][L]

    def subject_said(self, a: dict, q: str) -> bool:
        """Does the question name what the atom is about (its object / container / person / place)?"""
        p, args = a["pred"], a["args"]
        if p in ("on", "in", "held_by"):
            return _mentions_any(q, _obj_words(self.w, args[0]), self.w)
        if p in ("open", "closed", "robot_at"):
            return _mentions_any(q, _place_words(self.w, args[0]), self.w)
        if p == "robot_at_any":
            return any(_mentions_any(q, _place_words(self.w, x), self.w) for x in args)
        if p == "docked":
            return any(k in q.lower() for k in DOCK_WORDS)
        if p == "said_to":
            return _mentions_any(q, _person_words(self.w, args[0]), self.w)
        return False

    def covered(self, a: dict, q: str) -> bool:
        """Does the question (a read-back of the plan) state this atom the way the user asked for it?"""
        p, args = a["pred"], a["args"]
        if p in ("on", "in"):
            if not (self.subject_said(a, q) and _mentions_any(q, _place_words(self.w, args[1]), self.w)):
                return False
            if p == "in" and said_on_top(self.w, " , ".join(self.object_parts(q, args[0])) or q, args[1]):
                # "put the apple ... on the fridge" for "in the fridge": on top of it (gate pilot round 1,
                # hl-dev-000006 / 000005 / 000014: SAGE's goal was on(apple, fridge) and its gate then refused Open)
                return False
            return True
        if p in ("open", "closed") and not any(b["pred"] in ("on", "in") and b["args"][1] == args[0]
                                                for b in self.atoms):
            # opening (closing) is the request itself: the container must be said with the verb; "put the microwave
            # in the kitchen" names the microwave but does not open it (gate pilot round 1, hl-dev-000000 KO:
            # '요리용 마이크로웨이브를 주방에 두겠습니다' got yes). With something to be put in it ("open the fridge and put
            # the plate inside"), naming the container is enough, as before
            return self.subject_said(a, q) and said_with_verb(self.w, q, args[0], "open" if p == "open" else "close")
        if p == "held_by":
            if not self.subject_said(a, q):
                return False
            put = self._put_down_for(args[0], args[1], q, a.get("mode"))
            if put is not None:
                return put
            if args[1] == self.user_id:
                # to the speaker: "to you" / "to me", their place, or their own name ("the user", "grandma"; the
                # robot may name the person it talks to, pilot round 1 hl-dev-000010), never an id
                return self._to_speaker_said(args[0], q) or self._person_ok(args[1], q, obj=args[0])
            return self._person_ok(args[1], q, obj=args[0])
        if p == "said_to":
            # to the person (not "your husband is the one saying it", pilot round 2 hl-dev-000013 KO), and a quoted
            # message is the one asked for (the same keywords a Say must have for said_to to hold)
            if speech_role(self.w, args[0], q) == "speaker":
                return False
            quoted = quoted_texts(q)
            if quoted:
                from homeloop_robot.catalog import MESSAGES, message_matches  # robot core
                if args[1] in MESSAGES and not any(message_matches(args[1], t, detect_lang(t)) for t in quoted):
                    return False
            return self._person_ok(args[0], q)
        return self.subject_said(a, q)

    def _put_down_for(self, oid: str, pid: str, q: str, mode) -> "bool | None":
        """A delivery read back as a put-down ("put the red mug on the armchair"): False when the place it is put on
        is the person's own seat, bed or the floor (not a support surface; gate pilot round 1, hl-dev-000011 /
        000005 / 000018 / 000024: grandma on the armchair said yes to the mug "on the armchair", mom in bed to the
        vitamins "on the bed"), True when it is a support surface the person can reach where they are now and they
        asked for it to be brought (mode reach: "on the side table" beside grandma got "No, bring the red mug to
        me."), None otherwise (the other rules decide). Only this object's own part of the read-back counts, without
        the places said as its source or a waypoint, and a part that names another person is not a put-down for
        this one."""
        q = QUOTED_RX.sub(" ", unicodedata.normalize("NFC", str(q or "")))
        parts = self.object_parts(q, oid)
        if not parts:
            return None
        own = strip_route_places(self.w, " , ".join(parts))
        here = self.place_of(pid)
        pl = self.w.house.places.get(here) if here else None
        if pl is not None and not _is_support(pl) and said_put_on(self.w, own, here):
            return False
        if mode != "reach":
            return None
        bare = _blank(own, _obj_words(self.w, oid))
        if any(_mentions_any(bare, _person_words(self.w, x), self.w) for x in sorted(self.w.people) if x != pid):
            return None
        from homeloop_robot.reach import place_reachable  # robot core
        for k in sorted(self.w.house.places):
            if said_put_on(self.w, own, k) and place_reachable(self.w, k, pid):
                return True
        return None

    def object_parts(self, q: str, oid: str) -> list[str]:
        """The parts of a read-back that are about object ``oid``: a clause (or sentence) that names it, and the
        clauses after it up to the next one naming another object, or another part's place or person, of the request
        ('안경을 가져와서 / 드릴게요': the second clause is still about the glasses; '..., 리모컨은 할아버지께 드릴게요': that one
        is about the remote)."""
        mine = _obj_words(self.w, oid)
        others = [_obj_words(self.w, o) for o in self.objects() if o != oid]
        # ... or another part's place or person ("..., then open the fridge", "..., then tell grandpa")
        for a in self.atoms:
            if a["pred"] in ("on", "in", "held_by") and a["args"][0] == oid:
                continue
            for x in a.get("args") or []:
                if isinstance(x, str) and x in self.w.house.places:
                    others.append(_place_words(self.w, x)[:2])
                elif isinstance(x, str) and x in self.w.people and x != self.user_id:
                    others.append(_person_words(self.w, x))
        out, cur = [], False
        for cl in read_back_clauses(SENTENCE_RX.sub(",", q)):
            if _mentions_any(cl, mine, self.w):
                cur = True
            elif any(_mentions_any(cl, ws, self.w) for ws in others):
                cur = False
            if cur:
                out.append(cl)
        return out

    def _to_speaker_said(self, oid: str, q: str) -> bool:
        """Does the read-back say ``oid`` goes to the speaker ("to you", "hand it", '드릴게요', '당신', '손에') in that
        object's own part, with no other person and no place or room of another room said for it there? A "to me"
        word of another part of a compound read-back is not one for this object ('안경을 거실 탁자에 두고, 리모컨은
        할아버지께 드릴게요': the humble giving verb is for grandpa; fresh pilot round 3, hl-dev-000060 KO)."""
        q = QUOTED_RX.sub(" ", unicodedata.normalize("NFC", str(q or "")))
        here = self.place_of(self.user_id)
        pl = self.w.house.places.get(here) if here else None
        my_room = getattr(pl, "room", None)
        o = self.w.objects.get(oid)
        sources = {x for x in ((o.at if o else None), (getattr(self.w, "initial_at", None) or {}).get(oid))
                   if x in self.w.house.places}
        others = [p for p in sorted(self.w.people) if p != self.user_id]
        parts = self.object_parts(q, oid)
        # a "to me" word in a clause naming no other person ("give it to grandpa", '할아버지께 드릴게요' are not)
        if not any((ME_RX["en"].search(cl.lower()) or ME_RX["ko"].search(cl))
                   and not any(_mentions_any(cl, _person_words(self.w, p), self.w) for p in others) for cl in parts):
            return False
        part = " , ".join(parts)
        pd = strip_route_places(self.w, part)
        if my_room is not None and any(
                _mentions_any(pd, _place_words(self.w, k)[:2], self.w) for k in sorted(self.w.house.places)
                if k not in sources and k != here and self.w.house.places[k].room != my_room):
            return False                       # '거실 탁자에 두고' for a speaker in the small room
        if my_room is not None and any(room_said_as_dest(self.w, part, r) for r in sorted(self.w.house.rooms)
                                       if r != my_room):
            return False                       # '거실에 바로 올려서 당신이 ...', "to the living room"
        return True

    def _person_ok(self, pid: str, q: str, obj: str | None = None) -> bool:
        """The person is named, or their place is; a place named for them must be where they are. ``obj``: the
        object brought to them, whose own place may be named as where it comes from ("the mug from the counter")."""
        # a quoted message is what will be said, not where: "say 'It's time for bed.'" names no bed (fresh pilot round
        # 1, hl-dev-000057 EN), as in speech_role; it may still name its listener ('"점심 준비됐어요, 아빠."')
        named = _mentions_any(q, _person_words(self.w, pid), self.w)
        q0 = unicodedata.normalize("NFC", str(q or ""))
        q = QUOTED_RX.sub(" ", q0)
        here = self.place_of(pid)
        at_here = bool(here and _mentions_any(q, _place_words(self.w, here), self.w))
        # a place named for another part of the request (a compound read-back: "put the remote on the TV stand,
        # then tell grandpa") is not a place named for this person
        others = {x for a in self.atoms if a["pred"] not in ("said_to", "held_by")
                  for x in (a.get("args") or []) if x in self.w.house.places}
        # where the objects of the request are / were at the start: the sources of the deliveries, this one's and
        # the other objects' ("the glasses from the TV stand ..., then the remote ... to grandpa": the TV stand is
        # the glasses' source, not a place for grandpa; fresh pilot round 1, hl-dev-000060)
        objs = {x for a in self.atoms if a["pred"] in ("on", "in", "held_by") for x in a["args"][:1]}
        if obj is not None:
            objs.add(obj)
        sources = set()
        for o in sorted(x for x in objs if x in self.w.objects):
            sources |= {x for x in (self.w.objects[o].at, (getattr(self.w, "initial_at", None) or {}).get(o))
                        if x in self.w.house.places}
        others |= sources
        places = sorted(self.w.house.places)
        dock = getattr(self.w.house, "dock", None)
        if dock in self.w.house.places and any(a["pred"] == "docked" for a in self.atoms):
            others.add(dock)                     # "..., then go to the dock": the docked part of the request
        if obj is None:
            # a message: the places said in its own part of the read-back (the clause that says it, and a go-to
            # clause right before it), not those of the other parts ("..., then go to the fridge in the kitchen,
            # then put the vitamins ..., then go to the dock": gate pilot round 1, hl-dev-000024, every read-back got
            # "No, I asked you to tell the kid.")
            mq = message_part(self.w, q0, pid)
            other_place = any(_mentions_any(mq, _place_words(self.w, k)[:2], self.w) for k in places
                              if k != here and k not in others)
            return at_here or (named and not other_place)
        # a delivery: the person's place said only as a waypoint ("go to the desk_chair, then put the book on the
        # grandpa") is not where the object goes, and a part of the read-back that brings the object to another
        # person is not one for this person (gate pilot round 1, hl-dev-000018 EN: yes to the book "on the grandpa")
        at_here = bool(here and _mentions_any(strip_route_places(self.w, q), _place_words(self.w, here), self.w))
        parts = self.object_parts(q, obj)
        if parts:
            own = strip_route_places(self.w, " , ".join(parts))
            bare = _blank(own, _obj_words(self.w, obj))
            if not _mentions_any(bare, _person_words(self.w, pid), self.w) and any(
                    _mentions_any(bare, _person_words(self.w, x), self.w) for x in sorted(self.w.people)
                    if x != pid and x != self.user_id):
                return False
        # a delivery: a place said as where an object comes from or where the robot goes on the way ("the remote from
        # the coffee table", "go to the desk chair, then ...", '커피 테이블에 있는 리모컨', '의자에 가서') is not where it
        # is brought, even when that source is wrong (fresh pilot round 2, hl-dev-000060: the wrong source of the
        # remote and the speaker's seat in a go-to clause made a right delivery to grandpa "not covered")
        qd = strip_route_places(self.w, q)
        other_place = any(_mentions_any(qd, _place_words(self.w, k)[:2], self.w) for k in places
                          if k != here and k not in others)
        # ... but a place said in this object's own part of the read-back is where it goes, also when it is the place
        # of another part of the request ('... 주방 카운터에 있는 물병을 거실 TV 스탠드에 두는 거죠?': the TV stand,
        # the book's destination, is said for the water bottle brought to the speaker)
        for cl in read_back_clauses(q):
            if other_place:
                break
            if _mentions_any(cl, _obj_words(self.w, obj), self.w):
                cd = strip_route_places(self.w, cl)
                other_place = any(_mentions_any(cd, _place_words(self.w, k), self.w) for k in places
                                  if k != here and k not in sources)
        return at_here or (named and not other_place)


def _is_support(pl) -> bool:
    from homeloop_robot.reach import is_support  # robot core
    return is_support(pl)


def _blank(text: str, words) -> str:
    """``text`` with the given names blanked out (an object's own name may hold a person word: "grandpa's mug")."""
    t = str(text or "")
    for w in sorted({x for x in words if x}, key=len, reverse=True):
        t = re.sub(re.escape(w), " " * len(w), t, flags=re.I)
    return t


def _name_spans(world: Any, text: str, pid: str):
    """(start, end, word) of every name of place ``pid`` in ``text`` (longer names first, no overlaps)."""
    t = unicodedata.normalize("NFC", str(text or ""))
    taken, out = [], []
    for w in sorted(_place_words(world, pid), key=len, reverse=True):
        ko = detect_lang(w) == "ko"
        rx = re.compile(re.escape(w) if ko else r"(?<![\w])" + re.escape(w) + r"(?![\w])", 0 if ko else re.I)
        for m in rx.finditer(t):
            if not any(a < m.end() and m.start() < b for a, b in taken):
                taken.append(m.span())
                out.append((m.start(), m.end(), w))
    return t, out


# "on / onto / in / into (the) X" (EN, before the name); 'X에 / X 위에 / X 안에 ... 놓 / 두 / 둘 / 올려 / 넣 ...' (KO, after it)
EN_PUT_BEFORE_RX = re.compile(r"\b(?:on|onto|on\s+top\s+of|in|into|inside)\s+(?:the\s+|your\s+|my\s+|his\s+|her\s+)?$", re.I)
KO_PUT_AFTER_RX = re.compile(r"^\s*(?:(?:위|안|속)\s*)?(?:에다가?|에)\s*(?:\S+\s+)?(?:놓|놔|두|둘|둬|올려|올리|올릴|내려|넣)")
EN_ON_TOP_BEFORE_RX = re.compile(r"\b(?:on|onto|on\s+top\s+of)\s+(?:the\s+|your\s+|my\s+)?$", re.I)
KO_ON_TOP_AFTER_RX = re.compile(r"^\s*위\s*에")


def _after(t: str, b: int) -> str:
    """The text after a Korean name, without a clause mark the split put there ('냉장고 , 위에': a name ending in 고 / 서
    is cut by :data:`CLAUSE_RX`, and the parts were joined with ' , ')."""
    return re.sub(r"^\s*,\s*", " ", t[b:])


def said_put_on(world: Any, text: str, pid: str) -> bool:
    """Is place ``pid`` said in ``text`` as where something is put down ("on the armchair", "into the drawer",
    '안락의자에 놓을게요', '침대 위에 둘게요')? "to the armchair" / '안락의자로 가져다 드릴게요' (bring it there) is not."""
    t, spans = _name_spans(world, text, pid)
    for a, b, w in spans:
        if detect_lang(w) == "ko":
            if KO_PUT_AFTER_RX.match(_after(t, b)):
                return True
        elif EN_PUT_BEFORE_RX.search(t[:a]):
            return True
    return False


def said_on_top(world: Any, text: str, pid: str) -> bool:
    """Is container ``pid`` said in ``text`` as a surface something goes ON ("on the fridge", '냉장고 위에'), and nowhere
    as where it goes in ("in / into the fridge", '냉장고에 넣', '냉장고 안에')?"""
    t, spans = _name_spans(world, text, pid)
    on = inside = False
    for a, b, w in spans:
        if detect_lang(w) == "ko":
            rest = _after(t, b)
            if KO_ON_TOP_AFTER_RX.match(rest):
                on = True
            elif re.match(r"^\s*(?:안|속)|^\s*에\s*(?:\S+\s+)?넣", rest):
                inside = True
        else:
            before = t[:a]
            if EN_ON_TOP_BEFORE_RX.search(before):
                on = True
            elif re.search(r"\b(?:in|into|inside)\s+(?:the\s+|your\s+|my\s+)?$", before, re.I):
                inside = True
    return on and not inside


VERB_RX = {"open": {"en": re.compile(r"\bopen", re.I), "ko": re.compile(r"열(?!쇠)")},
           "close": {"en": re.compile(r"\b(?:close|shut)", re.I), "ko": re.compile(r"닫")}}


def said_with_verb(world: Any, q: str, pid: str, verb: str) -> bool:
    """Does a clause (or sentence) of read-back ``q`` that names container ``pid`` say ``verb`` (open / close)?"""
    t = QUOTED_RX.sub(" ", unicodedata.normalize("NFC", str(q or "")))
    rx = VERB_RX[verb]
    cls = read_back_clauses(SENTENCE_RX.sub(",", t))
    others = [k for k in sorted(world.house.places) if k != pid]
    for i, cl in enumerate(cls):
        if not _mentions_any(cl, _place_words(world, pid), world):
            continue
        # the clause that names it, and the next one when that names no other place ('마이크로웨이브 안에 들어가서 /
        # 문을 열어드릴까요?', sim-user audit q0092)
        nxt = cls[i + 1] if i + 1 < len(cls) else ""
        if nxt and any(_mentions_any(nxt, _place_words(world, k)[:2], world) for k in others):
            nxt = ""
        if any(rx["en"].search(x) or rx["ko"].search(x) for x in (cl, nxt) if x):
            return True
    return False


MESSAGE_CLAUSE_RX = {"en": re.compile(r"\b(?:say|says|saying|tell|telling|let\s+\w+\s+know|remind|inform|announce)\b",
                                      re.I),
                     "ko": re.compile(r"(?:말|전해|전하|전할|알려|알릴|여쭤)")}
GO_CLAUSE_RX = re.compile(r"\b(?:go|goes|going|move|moving|head|heading)\b|가서|가고|이동", re.I)


def message_part(world: Any, q: str, pid: str) -> str:
    """The part of read-back ``q`` that says the message to ``pid``: the clauses that hold the quoted message or a
    say / tell verb, each with a go-to clause right before it (where it is said); the whole text (quotes blanked)
    when no clause says one."""
    t = QUOTED_RX.sub(" «msg» ", unicodedata.normalize("NFC", str(q or "")))
    cls = read_back_clauses(SENTENCE_RX.sub(",", t))
    keep = set()
    for i, cl in enumerate(cls):
        if "«msg»" in cl or MESSAGE_CLAUSE_RX["en"].search(cl) or MESSAGE_CLAUSE_RX["ko"].search(cl):
            keep.add(i)
            # where it is said: a go-to clause right before it, or a Korean 'X에서' that the clause split cut off
            # ('침실 침대에서 / “...”라고 말할 거예요', sim-user audit q0373)
            if i > 0 and (GO_CLAUSE_RX.search(cls[i - 1]) or re.search(r"에서\s*$", cls[i - 1])):
                keep.add(i - 1)
    if not keep:
        return t.replace("«msg»", " ")
    return " , ".join(cls[i] for i in sorted(keep)).replace("«msg»", " ")


# A place named as a source or a waypoint: "from (the) X", "go / move / head to (the) X" (English, the words before
# the name); 'X에 있는', 'X에 놓인', 'X 위에 있는', 'X에 가서', 'X(으)로 가서' (Korean, the particles after it). Not 'X에서':
# it is also where the robot does something ('침대에서 ... 말할게요', sim-user audit q0373)
EN_ROUTE_BEFORE_RX = re.compile(r"\b(?:from|(?:go|goes|going|move|moving|head|heading)\s+(?:over\s+)?to)\s+"
                                r"(?:the\s+|your\s+|my\s+)?$")
KO_ROUTE_AFTER_RX = re.compile(r"^\s*(?:(?:위|안)?에\s*(?:있는|있던|놓인|놓여\s*있는|가서|가서요)|(?:으로|로)\s*(?:가서|이동))")


CLAUSE_RX = re.compile(r"[,;]|\bthen\b|\band\b|그리고|다음에|(?<=[고서])\s")


def read_back_clauses(q: str) -> list[str]:
    """The parts of a compound read-back (split at commas, "then", "and", '그리고', '...고 ', '...서 ')."""
    return [c for c in CLAUSE_RX.split(str(q or "")) if c and c.strip()]


SENTENCE_RX = re.compile(r"(?<=[.?!])\s+")


def room_said_as_dest(world: Any, q: str, rid: str) -> bool:
    """Is room ``rid`` said in ``q`` as where something goes? Korean: the room name with 에 / 에다 / (으)로, not 'X에
    있는' (:data:`KO_ROUTE_AFTER_RX`); English: "to / into the <room>", or "in the <room>" not right after a place
    name ("the TV stand in the living room" says where the TV stand is)."""
    room = world.house.rooms.get(rid)
    if room is None:
        return False
    t = unicodedata.normalize("NFC", str(q or ""))
    ko = [w for w in [room.name.get("ko")] if w]
    for w in ko:
        for m in re.finditer(re.escape(w) + r"(?:에다|에|으로|로)(?![가-힣])", t):
            if not KO_ROUTE_AFTER_RX.match(t[m.start() + len(w):]):
                return True
    en = [w for w in dict.fromkeys([room.name.get("en", ""), rid.replace("_", " ")]) if w]
    low = t.lower()
    pwords = sorted({x.lower() for k in world.house.places for x in _place_words(world, k) if detect_lang(x) == "en"},
                    key=len, reverse=True)
    for w in en:
        for m in re.finditer(r"\b(to|into|in)\s+the\s+" + re.escape(w.lower()) + r"(?:\s+room)?\b", low):
            before = low[:m.start()].rstrip()
            if m.group(1) != "in":
                if not re.search(r"\b(go|goes|going|move|moving|head|heading)(\s+over)?$", before):
                    return True
            elif not any(before.endswith(p) for p in pwords):
                return True
    return False


def strip_route_places(world: Any, q: str) -> str:
    """``q`` without the place names said as where an object comes from or where the robot goes on the way
    (:data:`EN_ROUTE_BEFORE_RX`, :data:`KO_ROUTE_AFTER_RX`); a place named as where something goes stays. The longer
    names go first, so "from the kid's desk" leaves no "desk"."""
    t = unicodedata.normalize("NFC", str(q or ""))
    words = sorted({w for k in getattr(world.house, "places", {}) for w in _place_words(world, k)}, key=len, reverse=True)
    for w in words:
        ko = detect_lang(w) == "ko"
        rx = re.compile(re.escape(w) if ko else r"(?<![\w])" + re.escape(w) + r"(?![\w])", 0 if ko else re.I)
        out, i = [], 0
        for m in rx.finditer(t):
            if (KO_ROUTE_AFTER_RX.match(t[m.end():]) if ko else EN_ROUTE_BEFORE_RX.search(t[:m.start()])):
                out += [t[i:m.start()], " " * len(m.group(0))]
                i = m.end()
        t = "".join(out) + t[i:]
    return t


# Who speaks to whom in a read-back of a message (pilot round 2, hl-dev-000013 KO: '남편이 “10분 있다가 나간다고 말해
# 주세요”라고 말하는 거죠?' = "your husband is the one who says this?"). The person named with a dative particle (남편한테,
# 남편에게, 할머니께) or after "tell / to" is the listener; named with a subject particle (남편이, 할머니께서) or before
# "will say / says", the speaker. The quoted message itself is left out (it may name people of its own).
# (an apostrophe inside an English word, "we're", is not a quote mark; a Korean particle may follow one: “...”라고)
QUOTED_RX = re.compile(r"(?<![A-Za-z0-9])[\'\"‘’“”「」『』]((?:[^\'\"‘’“”「」『』]|(?<=[A-Za-z])[\'’](?=[A-Za-z])){2,120})"
                       r"[\'\"‘’“”「」『』](?![A-Za-z])")
KO_LISTENER_RX = re.compile(r"^\s*(?:분\s*)?(?:한테|에게|께(?!서)|보고|더러)")
KO_SPEAKER_RX = re.compile(r"^\s*(?:분\s*)?(?:께서|이|가)(?![가-힣])")
EN_LISTENER_RX = r"\b(?:to|tell|telling|let|ask|asking|inform|remind)\s+(?:the\s+|your\s+|my\s+)?{w}\b"
EN_SPEAKER_RX = r"\b{w}\s+(?:will|is going to|is the one|says|said|wants to|would like to)\b"


def quoted_texts(q: str) -> list[str]:
    return [m.group(1).strip() for m in QUOTED_RX.finditer(unicodedata.normalize("NFC", str(q or "")))]


def speech_role(world: Any, pid: str, q: str) -> str | None:
    """"listener" / "speaker": the role ``q`` gives person ``pid`` outside quoted text; None when it says neither."""
    t = QUOTED_RX.sub(" ", unicodedata.normalize("NFC", str(q or "")))
    roles = set()
    for w in _person_words(world, pid):
        if detect_lang(w) == "ko":
            for m in re.finditer(re.escape(w), t):
                rest = t[m.end():]
                if KO_LISTENER_RX.match(rest):
                    roles.add("listener")
                elif KO_SPEAKER_RX.match(rest):
                    roles.add("speaker")
        else:
            low, ww = t.lower(), re.escape(w.lower())
            if re.search(EN_LISTENER_RX.format(w=ww), low):
                roles.add("listener")
            elif re.search(EN_SPEAKER_RX.format(w=ww), low):
                roles.add("speaker")
    if "listener" in roles:
        return "listener"
    return "speaker" if roles else None


# A robot's remark on its own understanding before a read-back (SAGE-v2 ``AssistLoop._read_back``: "I am not sure I
# understood (the X you mentioned is not in my plan; you did not say the Y)." and its Korean translations: "(당신이
# 말한 '나'는 제 계획에 없고 ...)", "냉장고 말씀하신 거 제가 이해한 게 맞는지 확신이 안 돼요.", "조리대 얘기한 거 제가 계획에
# 없고, ..."). It says what is NOT in the plan, so the things it names are not part of the read-back.
REMARK_PAREN_RX = re.compile(r"\s*[(（]([^()（）]*)[)）]")
REMARK_RX = {"en": re.compile(r"\bnot\s+sure\s+(?:if\s+|that\s+|whether\s+)?i\s+(?:understood|understand)\b|"
                              r"\bnot\s+in\s+my\s+plan\b|\byou\s+did(?:\s+not|n'?t)\s+(?:say|mention)\b", re.I),
             "ko": re.compile(r"계획에|계획엔|확신이\s*(?:안|없)|이해(?:한|했|하지|를)\s*(?:건지|게|것|는지|지|못)|모르겠|"
                              r"언급\s*(?:안|하지|없)|말씀\s*(?:안|하지\s*않)|얘기\s*안|포함(?:된|되지|하지)\s*(?:건|것|않)")}


def _remark(s: str) -> bool:
    return bool(REMARK_RX["en"].search(s) or REMARK_RX["ko"].search(s))


def strip_plan_remarks(question: str) -> str:
    """The question without the robot's remarks on what is not in its plan (the parentheticals and sentences
    :data:`REMARK_RX` finds); the text itself when nothing else is left."""
    q = str(question or "")
    t = re.sub(r"\.{2,}|…", ",", q)                     # "아들, 나, 아이, 저... 모두 제가 계획에 ...": one sentence
    t = REMARK_PAREN_RX.sub(lambda m: "" if _remark(m.group(1)) else m.group(0), t)
    keep = [s for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s and not _remark(s)]
    out = " ".join(keep).strip()
    return out if out else q


def message_room_answer(world: Any, gv: "GoalView", places: list, L: str, q: str | None = None) -> "Content | None":
    """"Which place do you mean: the counter in the kitchen or ... the stove in the kitchen?" when the kitchen is only
    in what the user asked the robot to SAY ("tell Grandpa to head to the kitchen"): the user says the message is the
    point, not a place there (gate pilot round 1, hl-dev-000015: it got "Grandpa is at the bed." twice); None when
    the offered places are not all in a room a message of the request names."""
    from homeloop_robot.catalog import MESSAGE_TEXT  # robot core
    rooms = {world.house.places[p].room for p in places if p in world.house.places}
    if len(rooms) > 1 and q is not None:
        # "drawer in the kitchen" also names the bedroom drawer: the rooms the question itself says
        rooms = {r for r in rooms if _mentions_any(q, [w for w in (world.house.rooms[r].name.get("en"),
                                                                   world.house.rooms[r].name.get("ko")) if w], world)}
    if len(rooms) != 1:
        return None
    room = world.house.rooms.get(next(iter(rooms)))
    if room is None:
        return None
    for a in gv.atoms:
        if a["pred"] != "said_to" or a["args"][1] not in MESSAGE_TEXT:
            continue
        msgs = MESSAGE_TEXT[a["args"][1]]
        if any(mentions(msgs.get(lg, ""), w, lg) for lg in ("en", "ko")
               for w in [room.name.get(lg, "")] if w):
            msg = msgs.get(L) or msgs.get("en", "")
            return Content("correct", _say("msg_not_place", L, person=person_name(world, a["args"][0], L),
                                           msg=msg.rstrip(".") if L == "ko" else msg), True, None, "goal_place_message")
    return None


def just_open_answer(world: Any, gv: "GoalView", text: str, L: str) -> "Content | None":
    """"Where should I put the microwave?" when the request only opens (closes) the microwave: "Please don't move it,
    just open the microwave." (gate pilot round 1, hl-dev-000000 KO: '마이크로웨이브를 어디에 두면 될까요?' got
    '전자레인지요.', and SAGE then planned to put the microwave on the microwave); None when ``text`` does not name
    such a container."""
    t = _q_text(text)
    for a in gv.atoms:
        if a["pred"] not in ("open", "closed") or a["args"][0] not in world.house.places:
            continue
        pid = a["args"][0]
        if any(b["pred"] in ("on", "in") and b["args"][1] == pid for b in gv.atoms):
            continue
        if str(text or "").strip() == pid or _mentions_any(t, _place_words(world, pid), world):
            return Content("correct", _say("just_open" if a["pred"] == "open" else "just_close", L,
                                           place=place_name(world, pid, L)), True, None, "goal_open")
    return None


def compose_from_goal(question: str, L: str, world: Any, gv: GoalView, *, knows_location: bool,
                      other_place: str | None = None, request: str | None = None) -> Content | None:
    """Answer content from what the user asked for, or None when no rule applies (see the section comment).
    ``request``: the user's own request text (the answer to "Should I do A first, or B?")."""
    if not gv.atoms:
        return None
    q = _q_text(question)
    qtype = classify(question)
    low = q.lower()
    goal_objs = [o for o in dict.fromkeys(gv.objects()) if _mentions_any(q, _obj_words(world, o), world)]
    alt = bool(ALT_RX.search(low))
    wrong_place = None
    if other_place is not None:
        key = "in" if getattr(world.house.places.get(other_place), "kind", "") == "container" else "on"
        wrong_place = _say(key, L, place=place_name(world, other_place, L))

    # 1. "Where should I put / bring the X?": where the user wants it
    is_dest = asks_destination(question)
    if is_dest and not goal_objs:
        c = just_open_answer(world, gv, q, L)
        if c is not None:
            return c
    if not goal_objs and is_dest:
        # "어디에 가져다줘야 할까요?" (Korean drops the object) / "Where should I put it?": the one thing asked for;
        # "Where should they go?" / "어디에 두면 될까요?" with several things asked for: where each one goes
        movers = [o for o in dict.fromkeys(gv.objects())]
        dests = {gv.dest_text(gv.dest(o), L) for o in movers}
        plural = L == "ko" or bool(re.search(r"\b(them|they|these|those|both|everything)\b|"
                                             r"\bthe (objects|things|items)\b", low))
        pron = plural or bool(re.search(r"\b(it|this|that)\b", low))
        if pron and movers and len(dests) == 1:
            return Content("correct", dests.pop(), True, wrong_place, "goal_destination")
        # a singular "it" with two things going to different places is still "which one?"
        if plural and len(movers) >= 2:
            return Content("correct", _dest_answer(gv, movers, L), True, wrong_place, "goal_destination")
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
                if any(mentions(q, n, lg, world) for lg in ("en", "ko") for n in object_names(world, o, lg)[:1])]
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

    # 2a. "Should I wake the kid first, or should I go to the fridge to grab the vitamins?": a choice between two
    # parts of the request (the order), not a yes / no question nor where one thing goes: the user says the request
    # again, in the order they asked for (gate pilot round 1, hl-dev-000024: it got "Yes, that's right.")
    if alt and qtype == "yes_no" and not READBACK_RX.search(q):
        sides = [x for x in ALT_RX.split(strip_plan_remarks(q), maxsplit=1) if x.strip()]
        said = [{i for i, a in enumerate(gv.atoms) if gv.subject_said(a, x)} for x in sides]
        # each side about another part ("bring the book and the phone to grandpa, or place them somewhere?" is one
        # part's place on both sides: rule 2b)
        if len(said) == 2 and said[0] and said[1] and said[0] - said[1] and said[1] - said[0]:
            return Content("correct", request, True, None, "goal_order") if request else None

    # 2b. "Should I put the X on A or on B?" / "bring it to you or put it somewhere?": where it goes
    about_where = bool(re.search(r"\b(put|place|bring|take|leave|move|give|hand|somewhere|where|to you)\b", low)
                       or re.search(r"(두|놓|놔|넣|가져|갖다|어디|드릴)", q)
                       or any(_mentions_any(q, _place_words(world, k)[:2], world) for k in sorted(world.house.places)))
    if goal_objs and alt and about_where and qtype in ("wh", "yes_no") and not READBACK_RX.search(q):
        return Content("correct", _dest_answer(gv, goal_objs, L), True, wrong_place, "goal_destination")

    # 3. "Which place do you mean: A or B or C?": the place the request names
    places = [pid for pid in sorted(world.house.places) if _mentions_any(q, _place_words(world, pid)[:2], world)]
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
            c = message_room_answer(world, gv, places, L, q)
            if c is not None:
                return c
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
        if not hits and knows_location:
            # none of the offered places is where the request goes, but one is where an object of the request is
            # now: that one, named so it is not taken for the other ("Which desk do you mean?" -> "The desk in the
            # study."; fresh pilot round 1, hl-dev-000016)
            src = [p for p in places for o in dict.fromkeys(gv.objects())
                   if o in world.objects and world.objects[o].at == p]
            if src:
                others = [p for p in places if p not in src]
                return Content("correct", _say("pick", L, name=clear_place_name(world, src[0], L)), True,
                               _say("pick", L, name=clear_place_name(world, others[0], L)) if others else None,
                               "goal_place")
        if hits:
            others = [p for p in places if p not in targets]
            return Content("correct", _say("pick", L, name=place_name(world, hits[0], L)), True,
                           _say("pick", L, name=place_name(world, others[0], L)) if others else None, "goal_place")

    # 3b. "Which place in the bedroom should I wait at?" when the user asked for the room, not a spot in it
    if qtype == "wh" or alt:
        for a in gv.atoms:
            if a["pred"] != "robot_at_any":
                continue
            rooms = {world.house.places[p].room for p in a["args"] if p in world.house.places}
            room = world.house.rooms.get(next(iter(rooms))) if len(rooms) == 1 else None
            if room is None:
                continue
            words = [w for w in (room.name.get("en"), room.name.get("ko"), room.id) if w]
            asks_place = re.search(r"\b(which|what|where)\b", low) or re.search(r"(어디|어느|어떤|무슨)", q)
            if asks_place and _mentions_any(q, words, world):
                return Content("correct", _say("anywhere_in", L, room=room.name.get(L, room.name.get("en", room.id))),
                               True, None, "goal_room")

    # 4. "Where is <person>?": where that person is now (a household member knows, unless they do not)
    if qtype == "wh" and (LOC_RX["en"].search(low) or LOC_RX["ko"].search(q) or "where" in low or "어디" in q):
        for pid in sorted(world.people):
            if pid != gv.user_id and _mentions_any(q, _person_words(world, pid), world):
                if not knows_location:
                    return Content("not_sure", TEXT["dont_know"][L], False, None, "location_unknown")
                here = gv.place_of(pid)
                if here:
                    txt = _say("person_at", L, person=person_name(world, pid, L), place=place_name(world, here, L))
                    return Content("correct", txt[:1].upper() + txt[1:], True, None, "person_location")

    # 5. yes / no: a read-back of the whole plan, or a question about one part of the request. A remark on what
    # the robot did not understand ("I am not sure I understood (the TV stand you mentioned is not in my plan).")
    # is not part of the plan read back: what it names is not checked against the request
    if qtype == "yes_no":
        q = strip_plan_remarks(q)
        readback = bool(READBACK_RX.search(q))
        rel = gv.atoms if readback else [a for a in gv.atoms if gv.subject_said(a, q)]
        if rel:
            bad = [a for a in rel if not gv.covered(a, q)]
            if not bad:
                return Content("yes", _say("yes", L), True, _say("no", L), "goal_confirm")
            return Content("no", gv.fix_text(bad[0], L, q), True, _say("yes", L), "goal_correct")
    return None
