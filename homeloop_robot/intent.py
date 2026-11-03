"""Structured robot questions (R2-7a, docs/user_model.md "Structured questions").

A planner may attach a *meaning* to a question: ``{"qtype": <one of QTYPES>, <slots>...}``. The simulated user
then picks its answer from the task script by qtype and slots (:func:`answer_structured`), instead of reading
the question text with the rules of ``dialog.compose``. The text the planner sends is still what the user hears
(it is logged and judged as an utterance); the answer goes through the same correct / wrong / not-sure mix,
silence, patience and ASR noise (``user.py``).

A question without a meaning (or with ``qtype: free``) is read by the rules (``dialog.compose``). When the rules
find nothing they understand (rule ``not_understood`` / ``generic_user``), an optional classifier (the bench's
LLM intent classifier, ``SimUser.classifier``) maps the text onto the same QTYPES plus slots; it only classifies,
the answer still comes from the script. Each answered question records its path: structured | rules | llm.

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
PATHS = ("structured", "rules", "llm")
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
            hit = [c for c in cands if any(D.mentions(text, p, lg) for lg in ("en", "ko")
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
        named = [o for o in objs if D._mentions_any(m["obj"], D._obj_words(world, o))]
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
        if pid != uid and D._mentions_any(obj, D._person_words(world, pid)):
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
        named = [a for a in atoms if D._mentions_any(person, D._person_words(world, a["args"][0]))]
        atoms = named or atoms
    if not atoms or atoms[0]["args"][1] not in MESSAGE_TEXT:
        return _not_sure(L, spec)
    return D.Content("correct", MESSAGE_TEXT[atoms[0]["args"][1]][L], True, None, "goal_message")


_WS = re.compile(r"\s+")


def normalize_question(q: str) -> str:
    """The key a classification is cached under (whitespace folded)."""
    return _WS.sub(" ", str(q or "")).strip()
