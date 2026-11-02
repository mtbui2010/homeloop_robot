"""robot_agent skill functions (legacy dict results) over the mock robot (docs/robot_agent.md).

Each is a plain ``def name(node, ..., **params) -> dict``: it calls ``get_backend().call(...)`` and
returns ``SkillResult.to_legacy()`` ({'isdone', 'msg', 'code'?} + data) with the shapes robot_agent
expects: find adds ``ins``, pose returns ``pose``, ask returns ``text``, grasp_check's isdone = holding.
"""

from __future__ import annotations

import re

from .backend import get_backend

_ID = re.compile(r"\b[a-z][a-z_]*_\d+\b")
DOCK_WORDS = {"dock", "charger", "home", "charging dock", "charging station", "base"}


def _name(world, oid: str) -> str:
    """An object as the robot's perception names it: colour + class ("pink cup"), never the world's id."""
    from ..catalog import CLASSES, COLORS
    o = world.objects[oid]
    c = CLASSES.get(o.cls)
    base = c.name["en"] if c is not None else o.cls.replace("_", " ")
    color = (o.attrs or {}).get("color")
    if color:
        color = (COLORS.get(color) or {}).get("en", color)
        if not base.startswith(f"{color} "):
            base = f"{color} {base}"
    return base


def _named(out: dict) -> dict:
    """The legacy result in the planner's words: object ids ('cup_2 not found', 'which one? (book_1, book_2)')
    become names ('pink cup not found', 'which one? (red book, blue book)'). A real robot reports what it saw,
    it has no world ids; an id in a message was copied by the LLM into its next step ('Find plate 1')."""
    world = getattr(get_backend(), "world", None)
    objs = getattr(world, "objects", None) or {}
    if not objs:
        return out
    sub = lambda m: _name(world, m.group(0)) if m.group(0) in objs else m.group(0)  # noqa: E731
    for k in ("msg", "found"):
        if isinstance(out.get(k), str):
            out[k] = _ID.sub(sub, out[k])
    if isinstance(out.get("candidates"), list):
        out["candidates"] = [_ID.sub(sub, str(x)) for x in out["candidates"]]
    return out


def _run(skill: str, **args) -> dict:
    return _named(get_backend().call(skill, **args).to_legacy())


def move(node=None, inputs: str = "", **params) -> dict:
    """MoveTo; to the charging dock it also docks: this robot's charger is a place, and a robot sent to its
    charger ends on it (as a robot vacuum's "go home"). robot_agent has no Dock goal: "go back and charge"
    is a MoveTo the dock."""
    out = _run("move", target=str(inputs))
    world = getattr(get_backend(), "world", None)
    dock = getattr(getattr(world, "house", None), "dock", None)
    target = str(inputs or "").strip()
    if out.get("isdone") and dock and (target == dock or target.lower() in DOCK_WORDS):
        d = _run("dock")
        if not d.get("isdone"):
            return d
        out["docked"] = True
    return out


def find(node=None, inputs: str = "", **params) -> dict:
    out = _run("find", obj=str(inputs))
    if out.get("isdone") and out.get("found"):
        out["ins"] = {out["found"]: {"pose_3d": [0.6, 0.0, 0.8]}}
    return out


def pick(node=None, inputs: str = "", **params) -> dict:
    return _run("pick", obj=str(inputs))


def place(node=None, inputs: str = "", **params) -> dict:
    return _run("place", target=str(inputs))


def put_in(node=None, inputs: str = "", **params) -> dict:
    return _run("put_in", container=str(inputs))


def open(node=None, inputs: str = "", **params) -> dict:  # noqa: A001 - the skill's name
    return _run("open", container=str(inputs))


def close(node=None, inputs: str = "", **params) -> dict:
    return _run("close", container=str(inputs))


def handover(node=None, inputs: str = "", **params) -> dict:
    return _run("handover", person=str(inputs or ""))


def wait_for_unload(node=None, inputs: str = "", **params) -> dict:
    """WaitForUnload: the nearest person takes the carried object (the handover skill)."""
    return _run("handover", person="")


def say(node=None, inputs: str = "", lang: str = "en", **params) -> dict:
    return _run("say", text=str(inputs), lang=str(lang or "en"))


def announce(node=None, inputs: str = "", lang: str = "en", **params) -> dict:
    return _run("announce", text=str(inputs), lang=str(lang or "en"))


def ask(node=None, inputs: str = "", lang: str = "en", retries: int = 0, **params) -> dict:
    out = {}
    for _ in range(max(0, int(retries or 0)) + 1):
        out = _run("ask", question=str(inputs), lang=str(lang or "en"))
        if out.get("isdone"):
            break
    out["text"] = out.get("answer", "")
    return out


def look(node=None, **params) -> dict:
    return _run("look")


def vlm_check(node=None, inputs: str = "", **params) -> dict:
    return _run("vlm_check", query=str(inputs))


def wait(node=None, inputs="5", **params) -> dict:
    try:
        s = float(inputs)
    except (TypeError, ValueError):
        s = inputs
    return _run("wait", seconds=s)


def dock(node=None, inputs: str = "dock", **params) -> dict:
    return _run("dock")


def grasp_check(node=None, **params) -> dict:
    out = _run("grasp_check")
    if out.get("code") is None:
        out["isdone"] = bool(out.get("holding"))
    return out


def pose(node=None, **params) -> dict:
    out = _run("pose")
    p = out.get("pose")
    if p:
        out["pose"] = (float(p[0]), float(p[1]), float(p[2]))
    return out
