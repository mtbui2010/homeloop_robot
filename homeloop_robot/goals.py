"""Goal-condition language: machine-checkable goals over the TRUE world (docs/world.md, Goals).

    {"all": [ATOM, ...]}                       conjunction (the top level is always "all")
    ATOM := {"pred": NAME, "args": [STR, ...]} | {"not": ATOM} | {"any": [ATOM, ...]}
    {"refuse": true, "all": [...]}             refuse task: the atoms say what must stay untouched
    {"stop": true, "all": []}                  stop goal set by the runner after a stop interruption
    {"pred": "delivered", "args": [OBJ, PERSON], "mode": "reach" | "hand", "mode_reason": null | "explicit" |
     "no_surface" | "user_needs"}              delivery to a person (homeloop_robot.reach.delivered)

Text form: ``on(mug_1, counter@kitchen) & not open(drawer@kitchen) & any(on(a, b) | on(a, c))``,
with an optional ``refuse:`` / ``stop:`` prefix; a delivery is ``delivered[reach](mug_1, grandma)`` (the
mode_reason is not part of the text form).

``held_by(obj, person)`` is kept for old data: it is the same as ``delivered[hand](obj, person)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .catalog import EXAMPLE_MESSAGES, MESSAGES, message_matches

PREDS = {
    "on": 2, "in": 2, "open": 1, "closed": 1, "robot_at": 1, "held_by": 2, "holding": 1,
    "hand_empty": 0, "docked": 0, "said_to": 2, "unmoved": 1, "delivered": 2,
}
# predicates whose first argument is an object that the goal moves
OBJECT_PREDS = ("on", "in", "held_by", "delivered")
# predicates that bring an object to a person
DELIVERY_PREDS = ("held_by", "delivered")


class GoalError(ValueError):
    pass


@dataclass(frozen=True)
class GoalEval:
    holds: bool
    atoms: tuple                     # ((atom_str, bool), ...) top-level atoms
    fraction: float                  # share of top-level atoms that hold (goal-condition success)


# ── text <-> JSON ─────────────────────────────────────────────────────────────────────────────────────

def _split_top(s: str, sep: str) -> list:
    out, depth, cur = [], 0, []
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                raise GoalError(f"unbalanced ')' in {s!r}")
        if ch == sep and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if depth != 0:
        raise GoalError(f"unbalanced '(' in {s!r}")
    out.append("".join(cur))
    return [x.strip() for x in out]


_ATOM_RE = re.compile(r"^([A-Za-z_]\w*)(?:\[(\w+)\])?\s*\((.*)\)$", re.S)


def _parse_atom(s: str) -> dict:
    s = s.strip()
    if not s:
        raise GoalError("empty atom")
    if s.startswith("not ") or s.startswith("!"):
        return {"not": _parse_atom(s[4:] if s.startswith("not ") else s[1:])}
    m = _ATOM_RE.match(s)
    if not m:
        if re.fullmatch(r"[A-Za-z_]\w*", s):
            return {"pred": s, "args": []}
        raise GoalError(f"not an atom: {s!r}")
    name, mode, inner = m.group(1), m.group(2), m.group(3)
    if name == "any":
        return {"any": [_parse_atom(x) for x in _split_top(inner, "|")]}
    args = [a.strip().strip("'\"") for a in _split_top(inner, ",")] if inner.strip() else []
    out = {"pred": name, "args": args}
    if mode is not None:
        out["mode"] = mode
    return out


def parse(text: str) -> dict:
    """Text form -> goal JSON."""
    t = (text or "").strip()
    goal: dict = {}
    for flag in ("refuse", "stop"):
        if t.lower().startswith(flag + ":"):
            goal[flag] = True
            t = t[len(flag) + 1:].strip()
    goal["all"] = [_parse_atom(x) for x in _split_top(t, "&")] if t else []
    return goal


def format_atom(a: dict) -> str:
    if "not" in a:
        return "not " + format_atom(a["not"])
    if "any" in a:
        return "any(" + " | ".join(format_atom(x) for x in a["any"]) + ")"
    mode = f"[{a['mode']}]" if a.get("mode") else ""
    return f"{a['pred']}{mode}({', '.join(a.get('args') or [])})"


def format(goal: dict) -> str:  # noqa: A001 - the design's name
    """Goal JSON -> canonical text (atoms in the given order)."""
    body = " & ".join(format_atom(a) for a in goal.get("all") or [])
    pre = "refuse: " if goal.get("refuse") else ("stop: " if goal.get("stop") else "")
    return (pre + body).strip()


def iter_preds(goal_or_atom):
    """Every positive/negated predicate atom inside a goal or atom (depth first)."""
    if "all" in goal_or_atom:
        for a in goal_or_atom["all"]:
            yield from iter_preds(a)
    elif "not" in goal_or_atom:
        yield from iter_preds(goal_or_atom["not"])
    elif "any" in goal_or_atom:
        for a in goal_or_atom["any"]:
            yield from iter_preds(a)
    else:
        yield goal_or_atom


# ── validation ────────────────────────────────────────────────────────────────────────────────────────

def validate(goal: dict, world) -> list:
    """Problems of a goal on a world (empty list = valid)."""
    errs = []
    if not isinstance(goal, dict) or not isinstance(goal.get("all"), list):
        return ["goal must be a dict with an 'all' list"]
    if not goal["all"] and not goal.get("stop"):
        errs.append("empty goal")
    places = world.house.places

    def obj(x, where):
        if x not in world.objects:
            errs.append(f"{where}: unknown object {x!r}")

    def place(x, where, kind=None):
        if x not in places:
            errs.append(f"{where}: unknown place {x!r}")
        elif kind == "container" and places[x].kind != "container":
            errs.append(f"{where}: {x} is not a container")
        elif kind == "not_container" and places[x].kind == "container":
            errs.append(f"{where}: {x} is a container (use in)")

    def chk(a):
        if not isinstance(a, dict):
            errs.append(f"atom {a!r}: not a dict")
            return
        if "not" in a:
            return chk(a["not"])
        if "any" in a:
            if not a["any"]:
                errs.append("any(): empty")
            for x in a["any"]:
                chk(x)
            return
        p, args = a.get("pred"), list(a.get("args") or [])
        w = format_atom(a) if p else repr(a)
        if p not in PREDS:
            errs.append(f"{w}: unknown predicate")
            return
        if len(args) != PREDS[p]:
            errs.append(f"{w}: {p} takes {PREDS[p]} args")
            return
        if p == "on":
            obj(args[0], w)
            place(args[1], w, "not_container")
        elif p == "in":
            obj(args[0], w)
            place(args[1], w, "container")
        elif p in ("open", "closed"):
            place(args[0], w, "container")
            if args[0] in places and places[args[0]].container and not places[args[0]].container.openable \
                    and p == "open":
                errs.append(f"{w}: {args[0]} cannot be opened")
        elif p == "robot_at":
            place(args[0], w)
        elif p in ("held_by", "delivered"):
            obj(args[0], w)
            if args[1] not in world.people:
                errs.append(f"{w}: unknown person {args[1]!r}")
            if p == "delivered":
                from .reach import MODE_REASONS, MODES
                if a.get("mode") not in MODES:
                    errs.append(f"{w}: mode must be one of {MODES}, not {a.get('mode')!r}")
                if a.get("mode_reason") not in MODE_REASONS:
                    errs.append(f"{w}: mode_reason must be one of {MODE_REASONS}, not {a.get('mode_reason')!r}")
                elif a.get("mode") == "reach" and a.get("mode_reason") is not None:
                    errs.append(f"{w}: mode reach has no mode_reason")
        elif p in ("holding", "unmoved"):
            obj(args[0], w)
        elif p == "said_to":
            if args[0] not in world.people:
                errs.append(f"{w}: unknown person {args[0]!r}")
            if args[1] not in MESSAGES and args[1] not in EXAMPLE_MESSAGES:
                errs.append(f"{w}: unknown message key {args[1]!r}")

    for a in goal["all"]:
        chk(a)
    return errs


# ── evaluation (TRUE state) ───────────────────────────────────────────────────────────────────────────

def holds(a: dict, world) -> bool:
    if "not" in a:
        return not holds(a["not"], world)
    if "any" in a:
        return any(holds(x, world) for x in a["any"])
    p, args = a["pred"], list(a.get("args") or [])
    objs = world.objects
    if p == "on":
        o = objs.get(args[0])
        pl = world.house.places.get(args[1])
        return bool(o and pl and o.at == args[1] and pl.kind != "container")
    if p == "in":
        o = objs.get(args[0])
        return bool(o and o.at == args[1] and o.inside)
    if p == "open":
        return args[0] in world.opened
    if p == "closed":
        return args[0] not in world.opened
    if p == "robot_at":
        return world.robot.at == args[0]
    if p == "held_by":
        o = objs.get(args[0])
        return bool(o and o.at == f"person:{args[1]}")
    if p == "delivered":
        from .reach import delivered
        return delivered(world, args[0], args[1], a.get("mode") or "hand")
    if p == "holding":
        return world.robot.holding == args[0]
    if p == "hand_empty":
        return world.robot.holding is None
    if p == "docked":
        return bool(world.robot.docked)
    if p == "said_to":
        # the listener understands the household's language (world.lang): "Dad, lunch is ready." said in a Korean
        # home does not tell dad (docs/world.md, Goals)
        lang = getattr(world, "lang", None)
        for u in world.utterances:
            if args[0] in u.heard_by and message_matches(args[1], u.text, lang or u.lang) and \
                    not relayed_request(world, args[0], u.text):
                return True
        return False
    if p == "unmoved":
        o = objs.get(args[0])
        return bool(o and o.at == world.initial_at.get(args[0]) and world.robot.holding != args[0])
    raise GoalError(f"unknown predicate {p!r}")


# A request to tell someone, said to that person ("남편한테 가서 10분 있다가 나간다고 말해 주세요." / "Let my husband know
# we're leaving in ten minutes." said to the husband): the user's request relayed word for word, not the message
# (pilot round 3, hl-dev-000013 KO; docs/world.md, Goals). It names the listener as the one to be told
# (``dialog.speech_role`` = listener) and asks or announces the telling (a tell verb; in Korean a quoted clause
# "...다고 / 라고" with a verb after it). A message that only names its listener ("남편한테 전화 왔어요.", "There is a
# call for you.") is delivered.
RELAY_RX = {"en": re.compile(r"\b(?:tell|telling|let\s+(?:\S+\s+){1,3}know|inform|remind|pass\s+(?:it|this|that)\s+on)\b",
                             re.I),
            "ko": re.compile(r"(?:[다라자냐래]고|라는\s*말을?)\s*\S{0,6}?\s*(?:주세요|줘|주시|줄래|드릴|드리|드려|할게|하겠)|"
                             r"(?:말해|말씀|전해|전달해|알려)\s*(?:주세요|줘|주시|줄래|드릴|드리|드려)")}


def relayed_request(world, pid: str, text: str) -> bool:
    """True when ``text`` said to ``pid`` is a request to tell ``pid`` (see :data:`RELAY_RX`)."""
    from .dialog import quoted_texts, speech_role
    if speech_role(world, pid, text) != "listener":
        return False
    t = str(text or "")
    for q in quoted_texts(t):
        t = t.replace(q, " ")
    return bool(RELAY_RX["en"].search(t) or RELAY_RX["ko"].search(t))


def evaluate(goal: dict, world) -> GoalEval:
    atoms = tuple((format_atom(a), bool(holds(a, world))) for a in goal.get("all") or [])
    n = len(atoms)
    ok = sum(1 for _, h in atoms if h)
    return GoalEval(holds=all(h for _, h in atoms), atoms=atoms, fraction=(ok / n) if n else 1.0)
