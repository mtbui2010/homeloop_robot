"""Structured robot questions (R2-7a, docs/user_model.md "Structured questions").

A planner may attach a *meaning* to a question: ``{"qtype": <one of QTYPES>, <slots>...}``. The simulated user
then picks its answer from the task script by qtype and slots (:func:`answer_structured`), instead of reading
the question text with the rules of ``dialog.compose``. The text the planner sends is still what the user hears
(it is logged and judged as an utterance); the answer goes through the same correct / wrong / not-sure mix,
silence, patience and ASR noise (``user.py``).

A question without a meaning (or with ``qtype: free``) is read by the rules (``dialog.compose``). When the rules
find nothing they understand (rule ``not_understood`` / ``generic_user``), an optional classifier (the bench's
LLM intent classifier, ``SimUser.classifier``) maps the text onto the same QTYPES plus slots; it only classifies,
the answer still comes from the script. Each answered question records its path: structured |
structured_mismatch (a Korean text that does not read as the meaning) | rules | llm.

The qtype list is frozen (docs/user_model.md). Slots:

==============  =====================================================================================
qtype           slots (all optional unless marked)
==============  =====================================================================================
which_object    options: [names], the objects offered ("the red mug or the blue mug"); obj
which_place     options: [place names / ids]; obj: the object whose destination is asked
confirm         goal: a read-back of the plan ("I will put the mug on the counter."); obj: one thing
                ("is it the red mug?"); options are not used
where_are_you   -
where_is        obj (required): an object or a person
repeat          about: request | answer (default: the request right after it, else the last answer)
did_you_mean    word (required): the word the robot heard
what_to_say     person: who the message is for
help            -: a request to clear the way / help with an obstacle
free            -: none of the above (the rules read the text)
==============  =====================================================================================
"""
from __future__ import annotations

import re
from typing import Any

from homeloop_robot import dialog as D

QTYPES = ("which_object", "which_place", "confirm", "where_are_you", "where_is", "repeat", "did_you_mean",
          "what_to_say", "help", "free")
SLOTS = {"which_object": ("options", "obj"), "which_place": ("options", "obj"), "confirm": ("goal", "obj"),
         "where_are_you": (), "where_is": ("obj",), "repeat": ("about",), "did_you_mean": ("word",),
         "what_to_say": ("person",), "help": (), "free": ()}
REQUIRED = {"where_is": "obj", "did_you_mean": "word"}
PATHS = ("structured", "structured_mismatch", "rules", "llm")
# the rules found nothing they understand: the classifier (when there is one) is asked
NOT_CONFIDENT = ("not_understood", "generic_user")

# compose() rule -> the qtype the rules read the question as (for the per-question record and the audit)
_RULE_QTYPE = {"self_position": "where_are_you", "repeat_answer": "repeat", "repeat_request": "repeat",
               "repair_confirm": "did_you_mean", "yes_no_intended": "confirm", "yes_no_other": "confirm",
               "goal_destination": "which_place", "goal_place": "which_place", "goal_room": "which_place",
               "person_location": "where_is", "location": "where_is", "location_unknown": "where_is",
               "goal_confirm": "confirm", "goal_correct": "confirm", "help": "help",
               "not_understood": "free", "generic_user": "free", "goal_message": "what_to_say"}

GO_TEXT = {"en": "To the {place}, please.", "ko": "{place}{ro} 가 주세요."}
NAMES_JOIN = {"en": " and the ", "ko": "하고 "}


def _hangul(s: str) -> bool:
    return any("가" <= ch <= "힣" for ch in str(s or ""))


def clean(meaning: Any) -> dict | None:
    """A planner's meaning as ``{"qtype", slots...}`` with only known slots of the right type, or None (no
    meaning, an unknown qtype, a required slot missing)."""
    if not isinstance(meaning, dict):
        return None
    qt = str(meaning.get("qtype") or "").strip()
    if qt not in QTYPES:
        return None
    out: dict = {"qtype": qt}
    for k in SLOTS[qt]:
        v = meaning.get(k)
        if v is None or v == "" or v == []:
            continue
        if k == "options":
            if isinstance(v, str):
                v = [v]
            if not isinstance(v, (list, tuple)):
                continue
            v = [str(x).strip() for x in v if str(x or "").strip()][:6]
            if v:
                out[k] = v
        elif k == "about":
            if str(v) in ("request", "answer"):
                out[k] = str(v)
        else:
            out[k] = str(v).strip()
    if qt in REQUIRED and REQUIRED[qt] not in out:
        return None
    return out


def rule_qtype(c: "D.Content", question: str, spec: dict | None) -> str:
    """The qtype the rules read ``question`` as, from the rule that answered it."""
    if c.rule in _RULE_QTYPE:
        return _RULE_QTYPE[c.rule]
    slot_q = "which_place" if (spec or {}).get("slot") == "destination" else "which_object"
    if c.rule == "clarify_answer":          # a wh question or one naming two or more candidates: a choice
        return slot_q
    if c.rule == "goal_object":             # "No, the red book." to "Did you mean the blue book?" is a check
        return "confirm" if c.kind in ("yes", "no") else "which_object"
    if c.rule == "scripted_answer":
        yn = D.classify(question) == "yes_no" and not D.ALT_RX.search(D._q_text(question).lower())
        return "confirm" if yn else slot_q
    return "free"


# ------------------------------------------------------------------------------------ canonical questions
# The answer functions of dialog.py read a question; a structured question is turned into the plain question of
# its qtype in the language of its slots (a Korean slot word in an English sentence would not be read as Korean)
CANON = {
    "which_object": {"en": "Which one do you mean: {opts}?", "ko": "{opts} 중에 어느 거요?"},
    "which_place": {"en": "Which place do you mean: {opts}?", "ko": "{opts} 중에 어느 곳이요?"},
    "dest_obj": {"en": "Where should I put the {obj}?", "ko": "{obj} 어디에 둘까요?"},
    "dest": {"en": "Where should I put it?", "ko": "어디에 둘까요?"},
    "confirm_obj": {"en": "Do you mean the {obj}?", "ko": "{obj} 맞아요?"},
    "confirm_goal": {"en": "{goal} Is that right?", "ko": "{goal} 맞죠?"},
    "where_is": {"en": "Where is the {obj}?", "ko": "{obj} 어디 있어요?"},
    "repeat": {"en": "Could you repeat that?", "ko": "다시 말씀해 주시겠어요?"},
    "repeat_request": {"en": "Could you repeat what you would like me to do?", "ko": "부탁하신 거 다시 말씀해 주시겠어요?"},
    "mean": {"en": "Did you mean \"{word}\"?", "ko": "\"{word}\"라고 하셨어요?"},
}
OR = {"en": " or ", "ko": ", 아니면 "}


def _canon(key: str, *slot_values, **kw) -> str:
    lg = "ko" if any(_hangul(v) for v in list(slot_values) + list(kw.values())) else "en"
    if "opts" in kw:
        kw["opts"] = OR[lg].join(kw["opts"])
    return CANON[key][lg].format(**kw)


# ------------------------------------------------------------------------------------ answers by qtype
def answer_structured(meaning: dict, L: str, spec: dict | None, world: Any, *, knows_location: bool,
                      other_place: str | None = None, user_place: tuple | None = None,
                      goal: "D.GoalView | None" = None, request: str | None = None,
                      last_answer: str | None = None) -> "D.Content | None":
    """The answer content for a cleaned meaning (:func:`clean`), or None for ``free`` (the rules read the text).
    Same keyword arguments as ``dialog.compose``."""
    m = meaning
    qt = m["qtype"]
    spec = spec or {}
    kw = dict(knows_location=knows_location, other_place=other_place)
    if qt == "free":
        return None
    if qt == "repeat":
        about = m.get("about")
        q = CANON["repeat_request" if about == "request" else "repeat"]["en"]
        c = D.repair(q, L, world, request=request, last_answer=None if about == "request" else last_answer,
                     goal=goal)
        return c if c is not None else _not_sure(L, spec)
    if qt == "where_are_you":
        if user_place is None:
            return _not_sure(L, spec)
        return D.Content("correct", D.self_position_text(world, user_place[0], bool(user_place[1]), L), False, None,
                         "self_position")
    if qt == "did_you_mean":
        q = _canon("mean", m["word"], word=m["word"])
        c = D.repair(q, L, world, request=request, last_answer=None, goal=goal, spec=spec) if request else None
        if c is not None:
            return c
        # not a word of the user's own request: a check of that thing ("Did you mean the blue book?")
        return answer_structured({"qtype": "confirm", "obj": m["word"]}, L, spec, world, user_place=user_place,
                                 goal=goal, request=request, last_answer=last_answer, **kw)
    if qt == "where_is":
        return _where_is(m["obj"], L, spec, world, goal, knows_location, other_place)
    if qt == "what_to_say":
        return _what_to_say(m.get("person"), L, spec, world, goal)
    if qt == "help":
        # a help request with no help-clearable fault (user.answer answers the other case before this)
        return _not_sure(L, spec)
    cands = spec.get("candidates") or []
    ans = spec.get("answer")
    intended = spec.get("intended")
    others = [c for c in cands if c.get("id") != intended]
    wrong = D.candidate_text(others[0], L) if others else None
    if qt == "which_object":
        if cands and ans and spec.get("slot") != "destination":
            return D.Content("correct", ans[L], True, wrong, "clarify_answer")
        if ans and not cands:
            return _scripted(spec, L)
        return _which_object(m, L, world, goal, kw) or _not_sure(L, spec)
    if qt == "which_place":
        if cands and ans and spec.get("slot") == "destination":
            return D.Content("correct", ans[L], True, wrong, "clarify_answer")
        if ans and not cands:
            return _scripted(spec, L)
        return _which_place(m, L, world, goal, kw) or _not_sure(L, spec)
    if qt == "confirm":
        text = m.get("goal") or m.get("obj") or ""
        if cands and ans:
            hit = [c for c in cands if any(D.mentions(text, p, lg, world) for lg in ("en", "ko")
                                           for p in (c.get("mentions") or {}).get(lg, []))]
            if len(hit) == 1:
                if hit[0].get("id") == intended:
                    return D.Content("yes", D.TEXT["yes"][L], True,
                                     D.TEXT["no"][L] + D.lower_first(wrong) if wrong else None, "yes_no_intended")
                return D.Content("no", D.TEXT["no"][L] + D.lower_first(ans[L]), True, D.TEXT["yes"][L],
                                 "yes_no_other")
        if ans and not cands:
            return _scripted(spec, L)
        if goal is not None and text:
            q = _canon("confirm_goal", text, goal=text) if m.get("goal") else _canon("confirm_obj", text, obj=text)
            c = D.compose_from_goal(q, L, world, goal, **kw)
            if c is not None:
                return c
        return _not_sure(L, spec)
    return None


def _not_sure(L: str, spec: dict) -> "D.Content":
    if not spec:
        return D.Content("not_sure", D.TEXT["dont_know"][L], False, None, "generic_user")
    return D.Content("not_sure", D.TEXT["not_sure"][L], False, None, "not_understood")


def _scripted(spec: dict, L: str) -> "D.Content":
    wt = spec.get("wrong_answer")
    return D.Content("correct", spec["answer"][L], True, wt[L] if isinstance(wt, dict) else None, "scripted_answer")


def _which_object(m: dict, L: str, world: Any, goal, kw) -> "D.Content | None":
    if goal is None:
        return None
    opts = m.get("options") or []
    if len(opts) >= 2:
        c = D.compose_from_goal(_canon("which_object", *opts, opts=opts), L, world, goal, **kw)
        if c is not None and c.rule == "goal_object":
            return c
    # "What should I bring?" (no options): the thing(s) the user asked for
    objs = list(dict.fromkeys(goal.objects()))
    if m.get("obj"):
        named = [o for o in objs if D._mentions_any(m["obj"], D._obj_words(world, o), world)]
        objs = named or objs
    if not objs:
        return None
    names = [D._specific_name(world, o, L) for o in objs[:2]]
    return D.Content("correct", D._say("pick", L, name=NAMES_JOIN[L].join(names)), True, None, "goal_object")


def _which_place(m: dict, L: str, world: Any, goal, kw) -> "D.Content | None":
    if goal is None:
        return None
    opts = m.get("options") or []
    obj = m.get("obj")
    if len(opts) >= 2 and not obj:
        c = D.compose_from_goal(_canon("which_place", *opts, opts=opts), L, world, goal, **kw)
        if c is not None:
            return c
    q = _canon("dest_obj", obj, obj=obj) if obj else _canon("dest")
    c = D.compose_from_goal(q, L, world, goal, **kw)
    if c is not None and c.rule == "goal_destination":
        return c
    if len(opts) >= 2:
        c = D.compose_from_goal(_canon("which_place", *opts, opts=opts), L, world, goal, **kw)
        if c is not None:
            return c
    # "Where should I go?" / "Which drawer should I open?": the place the request names
    for a in goal.atoms:
        if a["pred"] in ("robot_at", "robot_at_any"):
            name = D.place_name(world, a["args"][0], L)
            if a["pred"] == "robot_at_any":
                rooms = {world.house.places[p].room for p in a["args"] if p in world.house.places}
                if len(rooms) == 1 and next(iter(rooms)) in world.house.rooms:
                    room = world.house.rooms[next(iter(rooms))]
                    return D.Content("correct", D._say("anywhere_in", L, room=room.name.get(L, room.id)), True, None,
                                     "goal_room")
            txt = D._ko(GO_TEXT[L], place=name) if L == "ko" else GO_TEXT[L].format(place=name)
            return D.Content("correct", txt, True, None, "goal_place")
        if a["pred"] in ("open", "closed"):
            return D.Content("correct", D._say("pick", L, name=D.place_name(world, a["args"][0], L)), True, None,
                             "goal_place")
    return None


def _where_is(obj: str, L: str, spec: dict, world: Any, goal, knows_location: bool, other_place) -> "D.Content":
    objs = D.mentioned_objects(world, obj)
    if len(objs) > 1:
        want = [o for o in objs if o == spec.get("intended") or (goal is not None and o in goal.objects())]
        objs = want[:1] if len(want) == 1 else objs
    if len(objs) == 1:
        if not knows_location:
            return D.Content("not_sure", D.TEXT["dont_know"][L], False, None, "location_unknown")
        wrong = None
        if other_place is not None:
            key = "in" if getattr(world.house.places.get(other_place), "kind", "") == "container" else "on"
            wrong = D.TEXT[key][L].format(place=D.place_name(world, other_place, L))
        return D.Content("correct", D.location_text(world, objs[0], L), True, wrong, "location")
    for pid in sorted(world.people):
        uid = goal.user_id if goal is not None else None
        if pid != uid and D._mentions_any(obj, D._person_words(world, pid), world):
            if not knows_location:
                return D.Content("not_sure", D.TEXT["dont_know"][L], False, None, "location_unknown")
            here = goal.place_of(pid) if goal is not None else getattr(world.people[pid], "seat", None)
            if here:
                txt = D._say("person_at", L, person=D.person_name(world, pid, L), place=D.place_name(world, here, L))
                return D.Content("correct", txt[:1].upper() + txt[1:], True, None, "person_location")
    return _not_sure(L, spec)


def _what_to_say(person: str | None, L: str, spec: dict, world: Any, goal) -> "D.Content":
    from homeloop_robot.catalog import MESSAGE_TEXT
    atoms = [a for a in (goal.atoms if goal is not None else []) if a["pred"] == "said_to"]
    if person and len(atoms) > 1:
        named = [a for a in atoms if D._mentions_any(person, D._person_words(world, a["args"][0]), world)]
        atoms = named or atoms
    if not atoms or atoms[0]["args"][1] not in MESSAGE_TEXT:
        return _not_sure(L, spec)
    return D.Content("correct", MESSAGE_TEXT[atoms[0]["args"][1]][L], True, None, "goal_message")


_WS = re.compile(r"\s+")


def normalize_question(q: str) -> str:
    """The key a classification is cached under (whitespace folded)."""
    return _WS.sub(" ", str(q or "")).strip()


# ------------------------------------------------------------------------------------ free text: what the user hears
# How a person reads a free-text robot question before answering (R2-7a sim-user audit, docs/user_model.md
# "Free text"). Conventions of spoken dialog that the rules of ``dialog.compose`` did not have:
#
# 1. The robot's own re-ask preamble ("Sorry, I didn't hear you.", "죄송해요, 잘 안 들렸어요.") is not a request to
#    repeat, and "You mentioned the X." / "X 얘기하셨죠?" is context: the question after it is what is asked.
# 2. A compound question ("Where is the red book, and where should I bring it to?") is answered from its first
#    question, as people answer the first of several questions put at once.
# 3. An open "what should I do?" (nothing specific asked, or about a phrase that names nothing in the house) is a
#    request to say the task again; "what does 'X' mean?" about a quoted word is a check of a heard word.
# 4. "Where is X?" naming a thing or a person of the house (also after "I couldn't find X.") asks where it is;
#    "which drawer / 어떤 서랍" or a choice among places asks which place; a read-back ending in "맞죠?" / "Is that
#    right?" is a yes / no check; a remark with no question in it ("할아버지, 수건을 드립니다.") asks nothing.
PREAMBLE_RX = re.compile(
    r"^\s*(?:(?:sorry,?\s+i\s+(?:didn'?t|did\s+not)\s+hear\s+you\.|sorry,?\s+i\s+may\s+have\s+misheard\s+you\.|"
    r"죄송(?:해요|합니다)?,?\s*(?:잘\s*(?:안|못)\s*(?:들렸|들었)(?:어요|습니다)|잘\s*듣지\s*못했어요|"
    r"(?:혹시\s*)?제가\s*잘못\s*(?:들었을\s*수도\s*있어요|듣지\s*않았나요|들었나\s*봐요|들은\s*것\s*같아요))[.?]|"
    r"(?:혹시\s*)?제가\s*잘못\s*(?:들었을\s*수도\s*있어요|들은\s*것\s*같아요)\.)\s*)+", re.I)
# a sentence that only sets context for the question after it
CONTEXT_RX = re.compile(r"^(?:you mentioned (?:the )?.+\.|.+?(?:얘기|말씀)(?:하셨|하신)(?:죠|네요|군요|는데요?|던데요?)[?.,]?)$",
                        re.I)
# where a question sentence joins a second question
_JOIN_EN = re.compile(r",?\s+(?:and|or)\s+(?=(?:if so|where|what|which|who|how|should|shall|do|is|are|can)\b)|"
                      r",\s*(?=(?:and\s+)?if so\b)", re.I)
_JOIN_KO = re.compile(r"(?<=고)\s*,\s*|(?<=있고)\s+|,?\s*그리고\s+|,\s*아니면\s+(?=다른|그냥|혹시)")
_SENT_RX = re.compile(r"(?<=[.!?])\s+")

OPEN_DO_EN = re.compile(
    r"^(?:sorry\.?\s*)?(?:so\s+)?what(?:\s+exactly)?\s+(?:should|shall|do\s+you\s+want|would\s+you\s+like|can)\s+"
    r"(?:i|me|the\s+robot|it)(?:\s+to)?\s+(?:do|perform)\b(?P<rest>[^?]*)\??\s*$|"
    r"^what\s+(?:task|job)\s+(?:do|would)\s+you\b", re.I)
OPEN_REST_EN = re.compile(r"^\s*(?:exactly|there|here|now|next|first|for you|then)?\s*$", re.I)
OPEN_WITH_EN = re.compile(r"^\s*with\s+(?P<x>.+?)(?:\s+once\b.*|\s+there)?\s*$", re.I)
OPEN_DO_KO = re.compile(r"(?:어떤|무슨)\s*일을?\s*(?:해야|하면|할까|해\s*드릴)|(?:무엇|뭘|뭐)(?:을|를)?\s*(?:해야|하면|할까)|"
                        r"어떻게\s*(?:해야|하면|할까)")
# "which things / 어떤 물건" with nothing about them said, and an open "where?" in the same question
OPEN_WHAT_WHERE = {"en": re.compile(r"^(?:which|what)\s+(?:objects?|things?|items?)\b(?!\s+(?:by|in|on|from)\b).*"
                                    r"\bwhere\s+(?:should|do|would|shall)\b", re.I),
                   "ko": re.compile(r"(?:무슨|어떤|무엇)\s*(?:물건)?(?:을|를)?\s*(?:원하|옮|이동|두|놓|넣).*어디(?:에|로)?\s*"
                                    r"(?:두|놓|넣|가져|옮)|어디(?:에|로)?\s*(?:무엇|무슨|어떤)\s*(?:물건)?을?\s*(?:두|놓|넣)")}
MEAN_OF_EN = re.compile(r"\bwhat\s+do\s+you\s+mean\s+by\b|\bwhat\s+does\b.+\bmean\b|\bwhat\s+(?:is|are|was)\s+['‘\"“]|"
                        r"\bas\s+in\b|\b(?:did|do)\s+you\s+(?:mean|say)\s+['‘\"“]|\btypo\b", re.I)
MEAN_OF_KO = re.compile(r"(?:무슨|무엇을?|뭘|뭐)\s*(?:뜻|의미|말|가리키)|무엇인지|뭔지|무슨\s*말인지|어떤\s*물건을\s*말하|"
                        r"무엇을\s*의미|뜻이|뜻을|(?:이|)라고\s*(?:하셨|하신|말씀)")
QUOTE2_RX = re.compile(r"(?:^|(?<=[\s(]))['‘\"“「『]([^'’\"”」』]{1,80}?)['’\"”」』](?![A-Za-z])")
WHERE_IS_EN = re.compile(r"^where\s+(?:is|are)\s+(?P<obj>(?!you\b).+?)(?:\s+(?:located|now|right now))?\s*\??\s*$", re.I)
WHERE_IS_KO = re.compile(r"^(?P<obj>.+?)(?:은|는|이|가)?\s*(?:지금\s*)?어디(?:에)?\s*(?:있|계)")
POSITION_KO = re.compile(r"(?P<obj>.+?)(?:의)?\s*위치(?:를|가)?\s*(?:좀\s*)?(?:알려|말씀)")
NOT_FOUND = {"en": re.compile(r"\bi\s+(?:couldn'?t|could\s+not|can'?t|cannot)\s+find\s+(?P<obj>.+?)\.\s*$", re.I),
             "ko": re.compile(r"^(?P<obj>.+?)(?:을|를)?\s*(?:찾을\s*수(?:가)?\s*없|찾지\s*못)")}
WHERE_ANY = re.compile(r"\bwhere\b|어디", re.I)
SELF_WHERE_BARE_KO = re.compile(r"^(?:지금\s*)?어디(?:에요|예요|세요|계세요|야)\s*\??$")
TAG_RX = re.compile(r"^(?:is that (?:right|correct|ok(?:ay)?)|right|correct|ok(?:ay)?|맞(?:죠|아요|나요|습니까|지요)|괜찮(?:죠|을까요|아요))"
                    r"\s*\??$", re.I)
WHICH_EN = re.compile(r"\bwhich\s+(?P<x>[a-z ]+?)(?:\s+(?:do|should|did|would|in|on|of|to)\b|[?,])", re.I)
WHICH_KO = re.compile(r"(?:어느|어떤)\s*(?P<x>\S+?)(?:을|를|에|에서|이|가|인지)?(?=\s|\?|$)")
PLACE_NOUNS = ("place", "spot", "shelf", "drawer", "cabinet", "surface", "room", "곳", "장소", "선반", "서랍", "수납장",
               "칸", "자리", "방")
ALT_RX = re.compile(r"\bor\b|아니면|또는|이나\s|중\s*(?:에|하나)")
WH_ANY = re.compile(r"\b(?:which|what|where|who|whom|whose|how|when)\b|어느|어떤|어디|누구|뭐|무엇|무슨|어떻게|몇|언제",
                    re.I)
KO_Q_END = re.compile(r"(?:까요|나요|가요|죠|니|까|래요|ㄹ래요|을래요|할래요)\s*$")


def strip_preamble(question: str) -> str:
    """The question without the robot's re-ask preamble (convention 1); the text itself when nothing follows."""
    q = str(question or "")
    s = PREAMBLE_RX.sub("", q, count=1).strip()
    return s if s else q


def first_question(question: str, L: str, cut: bool = True) -> str:
    """The part of ``question`` that is answered (convention 2): the sentences up to its first question (the
    ones before it give context: "I will ... Is that right?"; a context-only sentence such as "You mentioned the
    X." is dropped), cut where that question joins a second one."""
    q = " ".join(str(question or "").split())
    sents = [x for x in _SENT_RX.split(q) if x]
    head = []
    for x in sents:
        if CONTEXT_RX.match(x) and len(sents) > 1:
            continue
        head.append(x)
        if x.endswith("?"):
            break
    if not head:
        head = sents[-1:] or [q]
    ctx, last = " ".join(head[:-1]), head[-1]
    rx = _JOIN_KO if _hangul(last) else _JOIN_EN
    parts = rx.split(last, maxsplit=1) if cut else [last]
    # a Korean "A하고, B하고, ..." lists steps of one question; it is cut only before a second wh question
    if len(parts) > 1 and rx is _JOIN_KO and not WH_ANY.search(parts[1]):
        parts = [last]
    if len(parts) > 1 and parts[0].strip():
        last = parts[0].rstrip(" ,") + "?"
    return (ctx + " " + last).strip()


def _quoted(q: str) -> list:
    return [x.strip() for x in QUOTE2_RX.findall(q) if x.strip()]


def _short(x: str) -> bool:
    return len(x.split()) <= 6 if not _hangul(x) else len(x.replace(" ", "")) <= 10


def _places_in(world: Any, text: str) -> list:
    t = D._q_text(text)
    return [pid for pid in sorted(world.house.places)
            if getattr(world.house.places[pid], "kind", "") != "floor" and D._mentions_any(t, D._place_words(world, pid), world)]


def _named(world: Any, x: str) -> bool:
    """Does ``x`` name a thing or a person of the house?"""
    x = D._q_text(x)
    return bool(D.mentioned_objects(world, x)) or any(D._mentions_any(x, D._person_words(world, pid), world)
                                                      for pid in sorted(world.people))


def _strip_obj(x: str) -> str:
    x = re.sub(r"^(?:the|your|my|a|an)\s+", "", x.strip(" ,.?"), flags=re.I)
    return re.sub(r"\s*(?:located|now)$", "", x)


def read_free(question: str, L: str, world: Any) -> tuple | None:
    """Conventions 1-4 for a free-text question: ``(meaning, rule)`` when one of them decides the reading, or None
    (the rules of ``dialog.compose`` read the text, see :func:`text_for_rules`)."""
    q = strip_preamble(question)
    if "?" not in q and not WH_ANY.search(q) and not KO_Q_END.search(q.rstrip(" .!")):
        return {"qtype": "free"}, "free_statement"          # a remark, no question in it
    head = first_question(q, L)
    sents = _SENT_RX.split(head)
    sent = sents[-1]                                     # the question sentence itself
    ctx = " ".join(sents[:-1])
    ko = _hangul(head)
    quoted = _quoted(head)
    mean_of = MEAN_OF_KO.search(head) if ko else MEAN_OF_EN.search(sent)
    if quoted and mean_of and not re.match(r"^\s*(?:which|어느|어떤)\b", sent, re.I):
        if _short(quoted[0]):
            return {"qtype": "did_you_mean", "word": quoted[0]}, "free_quoted_word"
        return {"qtype": "repeat", "about": "request"}, "free_quoted_request"
    # an open "what should I do (there)?"
    if not ko:
        m = OPEN_DO_EN.match(sent.strip())
        if m:
            rest = m.groupdict().get("rest") or ""
            w = OPEN_WITH_EN.match(rest)
            if OPEN_REST_EN.match(rest) or (w and not D._names_anything(world, w["x"])):
                return {"qtype": "repeat", "about": "request"}, "free_open_task"
    elif OPEN_DO_KO.search(sent) and not D.mentioned_objects(world, sent):
        return {"qtype": "repeat", "about": "request"}, "free_open_task"
    whole = _SENT_RX.split(first_question(q, L, cut=False))[-1]       # the question sentence, not cut
    if OPEN_WHAT_WHERE["ko" if ko else "en"].search(whole) and not D.mentioned_objects(world, whole):
        return {"qtype": "repeat", "about": "request"}, "free_open_task"
    # the robot asks the user to do the task ("Can you bring me the white mug?"): nothing to answer
    if (USER_TASK_KO.search(sent) if ko else USER_TASK_EN.match(sent.strip())):
        return {"qtype": "free"}, "free_user_task"
    # what message to give: "What should I tell grandpa?" / "할아버지께 뭐라고 말씀드릴까요?"
    if (SAY_WHAT_KO.search(sent) if ko else SAY_WHAT_EN.match(sent.strip())):
        who = [pid for pid in sorted(world.people) if D._mentions_any(sent, D._person_words(world, pid), world)]
        return ({"qtype": "what_to_say", "person": D.person_name(world, who[0], L)} if len(who) == 1 else
                {"qtype": "what_to_say"}), "free_what_to_say"
    # where is X? (also after "I couldn't find X.")
    nf = NOT_FOUND["ko" if _hangul(ctx) else "en"].search(ctx) if ctx else None
    if nf and WHERE_ANY.search(sent):
        return {"qtype": "where_is", "obj": _strip_obj(nf["obj"])}, "free_where_is"
    m = (WHERE_IS_KO.match(sent) or POSITION_KO.match(whole)) if ko else WHERE_IS_EN.match(sent.strip())
    if m and _named(world, m["obj"]) and not WH_ANY.search(m["obj"]):
        return {"qtype": "where_is", "obj": _strip_obj(m["obj"])}, "free_where_is"
    if ko and SELF_WHERE_BARE_KO.match(sent.strip()) and not (ctx and _named(world, ctx)):
        return {"qtype": "where_are_you"}, "free_where_are_you"
    # a read-back with a tag question: "I will put ... . Is that right?" / "... 넣을게요. 맞죠?"
    if ctx and TAG_RX.match(sent.strip()) and D.READBACK_RX.search(ctx):
        return {"qtype": "confirm", "goal": ctx}, "free_read_back"
    # where should it go: "점심 어디에 두면 돼요?"
    if ko and DEST_KO.search(sent) and not WHERE_IS_KO.match(sent):
        objs = D.mentioned_objects(world, sent)
        return ({"qtype": "which_place", "obj": D._specific_name(world, objs[0], L)} if len(objs) == 1 else
                {"qtype": "which_place"}), "free_destination"
    # which object: "Which object do you mean by 'the green one'?" / "어떤 거요?"
    if (WHICH_OBJ_KO.match(sent.strip()) if ko else WHICH_OBJ_EN.match(sent.strip())):
        return ({"qtype": "which_object", "obj": quoted[0]} if quoted else {"qtype": "which_object"}), "free_which_object"
    # a choice: "A or B?" between two things / two places of the house
    alts = [x for x in ALT_RX.split(whole) if x.strip()]
    if ko and len(alts) < 2 and len(re.findall(r"까요", whole)) >= 2:       # "A 드릴까요, B 드릴까요?"
        alts = [x for x in re.split(r"(?<=까요)\s*,\s*", whole) if x.strip()]
    if len(alts) >= 2:
        o2 = [_objects_in(world, x) for x in alts[-2:]]
        p2 = [_places_in(world, x) for x in alts[-2:]]
        if all(o2) and not any(p2) and o2[0] != o2[1]:
            return {"qtype": "which_object"}, "free_choice"
        if all(p2) and p2[0] != p2[1] and not any(o2[1:]):
            return {"qtype": "which_place"}, "free_choice"
    # which place: "which drawer / 어떤 서랍", or a choice among places only
    w = (WHICH_KO if ko else WHICH_EN).search(sent)
    if w and (any(n in w["x"].lower() for n in PLACE_NOUNS) or (_places_in(world, w["x"]) and not _named(world, w["x"]))):
        return {"qtype": "which_place"}, "free_which_place"
    if (w or ALT_RX.search(q)) and not D.mentioned_objects(world, q) and not (w and _thing_word(world, sent)):
        pl = _places_in(world, q)
        if len(pl) >= 2:
            return {"qtype": "which_place", "options": [D.place_name(world, p, L) for p in pl][:6]}, "free_which_place"
    # a proposal: "Should I ...?" / "...드릴까요?" (one action, no alternative, no wh word): a yes / no check
    if not ALT_RX.search(whole) and not WH_ANY.search(sent) and len(re.findall(r"까요", sent)) <= 1:
        if (not ko and PROPOSE_EN.match(sent.strip())) or (ko and PROPOSE_KO.search(sent.strip())):
            return {"qtype": "confirm", "goal": sent.strip()}, "free_proposal"
    return None


DEST_KO = re.compile(r"어디(?:에|로)?\s*(?:다\s*)?(?:두|놓|넣|갖다|가져다|가져가|옮기|옮겨)")
PROPOSE_EN = re.compile(r"^(?:should|shall)\s+(?:i|the robot|we)\b|^(?:do you want|would you like)\s+me\s+to\b", re.I)
PROPOSE_KO = re.compile(r"(?:드릴|해\s*드릴|할|갈|놓을|둘|넣을|줄|올|전할|말할|가져갈)까요\s*\??$|(?:해|말해|가져다|갖다)\s*줘요\s*\?$|"
                        r"(?:거|건|것)\s*(?:맞나요|맞죠|맞아요|죠)\s*\??$|되는\s*(?:건가요|거죠)\s*\??$")
SAY_WHAT_EN = re.compile(r"^what\s+(?:exactly\s+)?(?:should|shall|do\s+you\s+want|would\s+you\s+like)\s+(?:i|me)\s+(?:to\s+)?"
                         r"(?:say|tell)\b", re.I)
SAY_WHAT_KO = re.compile(r"(?:뭐|무엇|무슨\s*말)(?:이?라고|을|를)?\s*(?:전할|말할|말씀드릴|전해|말해|얘기할|전달할)")
WHICH_OBJ_EN = re.compile(r"^which\s+(?:object|one|thing|item)s?\b", re.I)
WHICH_OBJ_KO = re.compile(r"^(?:어느|어떤)\s*(?:거|것|걸|물건)(?:을|를|이|가|요)?(?=\s|\?|$)")
USER_TASK_EN = re.compile(r"^(?:can|could|would|will)\s+you\s+(?:please\s+)?(?:bring|get|fetch|put|take|give|grab|pick)\b",
                          re.I)
USER_TASK_KO = re.compile(r"(?:가져다|갖다|놓아|넣어|옮겨)\s*주실\s*(?:수\s*있|래)")


def _objects_in(world: Any, text: str) -> set:
    """Every object of the house the text names (not only the most specific)."""
    t = D._q_text(text)
    return {oid for oid in sorted(world.objects) for lg in ("en", "ko")
            for n in D.object_names(world, oid, lg) if n and D.mentions(t, n, lg, world)}
# generic words for a thing ("which object", "어떤 물건"): a which-question about them is not about a place
THING_WORDS = ("object", "item", "thing", "one", "물건", "거", "것", "걸")


def _thing_word(world: Any, text: str) -> bool:
    """Does the question name a kind of thing (a generic word, or the base name of a house object: "컵", "book")?"""
    t = D._q_text(text).lower()
    words = set(re.findall(r"[a-z]+|[가-힣]+", t))
    if words & set(THING_WORDS):
        return True
    for oid in sorted(world.objects):
        for lg in ("en", "ko"):
            for n in D.object_names(world, oid, lg):
                base = str(n).split()[-1].lower() if n else ""
                if base and (base in words or (lg == "ko" and any(w.startswith(base) for w in words))):
                    return True
    return False


def text_for_rules(question: str, L: str) -> str:
    """The text ``dialog.compose`` reads: the question without the re-ask preamble, its first question only
    (conventions 1-2). A repeat request stays whole ("Sorry, I didn't catch that. Could you say it again?")."""
    q = strip_preamble(question)
    return first_question(q, L) if "?" in q else q


def ungrounded(meaning: dict, world: Any, question: str = "") -> dict | None:
    """The meaning to use instead when a which-object / which-place meaning is about a phrase that names nothing
    in the house ("What should I do with the chicken bring?", an ASR fragment the robot took for an object), else
    None: a "where ...?" still asks where things go (the phrase is dropped); otherwise the person cannot answer
    about it and says the task again (convention 3)."""
    obj = meaning.get("obj")
    if meaning["qtype"] not in ("which_object", "which_place") or not obj or meaning.get("options") or \
            D.mentioned_objects(world, D._q_text(obj)):
        return None
    if meaning["qtype"] == "which_place" and WHERE_ANY.search(first_question(strip_preamble(question), "en")):
        return {"qtype": "which_place"}
    return {"qtype": "repeat", "about": "request"}
