"""Shared types of the mock robot: failure codes, skill results, user / safety protocols.

Both robot streams code against these definitions (docs/architecture.md). Pure stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Protocol, runtime_checkable


class FailureCode(str, Enum):
    """Why a skill failed. Values are identical to ``robot_agent.contract.FailureCode``
    (tests/test_types.py checks this when robot_agent is importable)."""
    ABSENT = "absent"
    PERCEPTION_UNAVAILABLE = "perception_unavailable"
    UNREACHABLE = "unreachable"
    BLOCKED = "blocked"
    GRASP_FAILED = "grasp_failed"
    DROPPED = "dropped"
    HW_FAULT = "hw_fault"
    ESTOP = "estop"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    SOFTWARE = "software"

    @classmethod
    def parse(cls, value) -> "FailureCode":
        if isinstance(value, cls):
            return value
        return cls(str(value).strip().lower())


def _r6(x):
    from .rng import r6
    return r6(x)


def _round_tree(v):
    """Round every float in a JSON-like tree to 6 decimals (deterministic output)."""
    if isinstance(v, float):
        return _r6(v)
    if isinstance(v, dict):
        return {str(k): _round_tree(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_round_tree(x) for x in v]
    if isinstance(v, Enum):
        return v.value
    return v


@dataclass(frozen=True)
class SkillResult:
    ok: bool
    code: Optional[FailureCode]      # None iff ok
    msg: str                         # English; robot_agent's classify_legacy_failure(msg) == code
    data: dict = field(default_factory=dict)     # evidence shown to the planner
    duration_s: float = 0.0
    injected: bool = False           # the outcome came from the failure model, not a true-state precondition
    truth: dict = field(default_factory=dict)    # hidden from planners: {"effect": bool, "event": ...}

    def public(self) -> dict:
        return {"ok": self.ok, "code": self.code.value if self.code else None, "msg": self.msg,
                "data": _round_tree(dict(self.data)), "duration_s": _r6(self.duration_s)}

    def to_legacy(self) -> dict:
        d = _round_tree(dict(self.data))
        d["isdone"] = bool(self.ok)
        d["msg"] = self.msg
        if self.code is not None:
            d["code"] = self.code.value
        return d

    def to_json(self) -> dict:
        d = self.public()
        d["injected"] = self.injected
        d["truth"] = _round_tree(dict(self.truth))
        return d


@dataclass(frozen=True)
class Call:
    skill: str
    args: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"skill": self.skill, "args": {k: self.args[k] for k in sorted(self.args)}}

    def __str__(self) -> str:
        a = ", ".join(f"{k}={self.args[k]!r}" for k in sorted(self.args))
        return f"{self.skill}({a})"


@dataclass(frozen=True)
class SkillSpec:
    name: str
    params: dict                     # JSON-schema-like {arg: {"type": ..., "default"?: ...}}
    required: tuple
    description: str
    motion: bool
    device: str                      # base | arm | camera | speaker | gripper | none


@dataclass
class FaultState:
    """A device / path / container fault that outlives one call (docs/failure_model.md)."""
    device: str                      # base | arm | camera | gripper | speaker | mic | path:<a>-><b> | container:<id> | grasp:<obj>
    code: FailureCode
    since_t: float
    clears_on: str                   # wait | retry | help | never
    p_clear: float                   # per wait / per retry / per help request
    p_help: float = 0.0              # an ask while active clears it with this p (0 = help does not clear)

    def to_json(self) -> dict:
        return {"device": self.device, "code": self.code.value, "since_t": _r6(self.since_t),
                "clears_on": self.clears_on, "p_clear": _r6(self.p_clear), "p_help": _r6(self.p_help)}


@dataclass(frozen=True)
class Utterance:
    t: float
    skill: str                       # say | announce | ask
    text: str
    lang: str
    heard_by: tuple                  # person ids


# ── user model (implemented by homeloop_robot.user.SimUser; NullUser in episode.py) ─────────────────────

@dataclass(frozen=True)
class UserReply:
    text: str
    kind: str                        # correct | wrong | not_sure | no_answer | yes | no
    latency_s: float
    heard_question: bool


@dataclass(frozen=True)
class Heard:
    text: str
    event: str                       # ok | not_heard | partial | corrupted


@dataclass(frozen=True)
class UserEvent:
    t: float
    kind: str                        # stop | correction
    text: str
    new_goal: Optional[dict] = None


@dataclass(frozen=True)
class PersonState:
    id: str
    pos: tuple
    vel: tuple
    room: Optional[str]
    awake: bool = True


@runtime_checkable
class UserModel(Protocol):
    def hear_instruction(self, text: str, lang: str) -> Heard: ...

    def answer(self, question: str, lang: str, robot_xy: tuple, t: float) -> tuple:
        """-> (UserReply, Heard): what the person says, and what the robot's ASR hears."""
        ...

    def take_handover(self, person_id: str, obj_id: str, t: float) -> tuple:
        """-> (taken: bool, latency_s: float)."""
        ...

    def hears(self, person_id: str, robot_xy: tuple, t: float, broadcast: bool) -> bool: ...

    def events_between(self, t0: float, t1: float) -> list: ...

    def people_at(self, t: float) -> dict: ...

    def help_request(self, question: str, t: float) -> None: ...


# ── safety monitor (implemented by homeloop_robot.safety.SafetyMonitor; NullSafety in episode.py) ───────

@dataclass(frozen=True)
class Violation:
    t: float
    skill: str
    person: str
    d: float
    s_p: float
    v_r: float
    v_h: float
    severe: bool
    cause: str


@dataclass(frozen=True)
class Traverse:
    """Result of one monitored motion.

    part="base": ``duration_s`` is the whole traverse time (nominal path time + slow-down + stops).
    part="arm": the Robot passes ``path=[robot_xy]`` and its arm speed; ``duration_s`` is read as the
    EXTRA time (slow-down + stops) that is added to the skill's nominal duration from the profile.
    ``aborted`` (a protective stop longer than the stop timeout) makes the skill fail ``blocked``."""
    duration_s: float
    slow_s: float
    stopped_s: float
    aborted: bool
    min_sep_m: Optional[float]
    violations: tuple = ()


@runtime_checkable
class SafetyMonitorProto(Protocol):
    def traverse(self, skill: str, path: list, v_nominal: float, t0: float,
                 people: Callable[[float], dict], *, part: str = "base",
                 collaborative_with: Optional[str] = None) -> Traverse: ...

    def stats(self) -> dict: ...


@dataclass(frozen=True)
class HazardEvent:
    t: float
    code: str
    skill: str
    args: dict
    why: str

    def to_json(self) -> dict:
        return {"t": _r6(self.t), "code": self.code, "skill": self.skill,
                "args": {k: self.args[k] for k in sorted(self.args)}, "why": self.why}
