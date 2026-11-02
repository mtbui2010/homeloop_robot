"""robot_agent skill functions (legacy dict results) over the mock robot (docs/robot_agent.md).

Each is a plain ``def name(node, ..., **params) -> dict``: it calls ``get_backend().call(...)`` and
returns ``SkillResult.to_legacy()`` ({'isdone', 'msg', 'code'?} + data) with the shapes robot_agent
expects: find adds ``ins``, pose returns ``pose``, ask returns ``text``, grasp_check's isdone = holding.
"""

from __future__ import annotations

from .backend import get_backend


def _run(skill: str, **args) -> dict:
    return get_backend().call(skill, **args).to_legacy()


def move(node=None, inputs: str = "", **params) -> dict:
    return _run("move", target=str(inputs))


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
