"""Failure model: how one skill call's stochastic outcome is drawn (docs/failure_model.md).

Every call draws a fixed vector of uniforms from ``rng_for(episode, "outcome", skill, canon_args, nth)``
(:func:`uniforms`); each rule reads its own slot, so the same call in two planners' episodes gets the
same numbers for the same rule (common random numbers) whatever branch the other rules took.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .types import FailureCode, FaultState

__all__ = ["Ctx", "Outcome", "FaultState", "uniforms", "p_fail", "p_retry_success", "split_code",
           "sample_outcome", "U", "N_UNIFORMS", "container_class"]


class U:
    """Slots of the per-call uniform vector."""
    HW = 0              # hardware fault on this call
    HW_PERSIST = 1      # ... and it persists for the episode
    FAIL = 2            # skill failure / retry success / flip / clear
    SPLIT = 3           # failure code from the split
    SILENT = 4          # silent failure (reports ok)
    PERC = 5            # false positive (find) / camera dropout ratio
    WRONG = 6           # wrong instance
    EXTRA = 7           # false arrival / drop while placing or handing over
    DUR = 8             # duration draw
    AUX = 9             # direction of a false arrival / which instance
    UNAVAIL = 10        # perception unavailable / move timeout
    CARRY = 11          # drop in transit
    ESTOP = 12          # random e-stop during a motion call
    FAILTIME = 13       # fraction of nominal time a failed call spends


N_UNIFORMS = 14


def uniforms(rng) -> list:
    return [rng.random() for _ in range(N_UNIFORMS)]


@dataclass(frozen=True)
class Ctx:
    skill: str
    clutter: str = "medium"              # target place clutter (move: target; pick/find: robot's place)
    grasp_class: Optional[str] = None
    container_type: Optional[str] = None
    hard_nav: bool = False
    tags: tuple = ()
    n_confusable: int = 0
    attempt: int = 1                     # 1 + previous failed attempts of the same (skill, args) in a row
    sticky: bool = False                 # previous attempt failed with a sticky fault still active


@dataclass(frozen=True)
class Outcome:
    kind: str                            # ok | fail | silent_fail | wrong_instance | false_positive
    code: Optional[FailureCode] = None
    event: Optional[str] = None


def container_class(container_type: Optional[str]) -> str:
    """Dobb-E rows: drawers are `drawer`; cabinet / fridge / appliance doors and box lids are `door`."""
    return "drawer" if container_type == "drawer" else "door"


def p_fail(profile, ctx: Ctx) -> float:
    s = ctx.skill
    if s == "move":
        return float(profile.get("move.p_fail")[ctx.clutter])
    if s == "pick":
        cls_map = profile.get("pick.p_fail_class")
        if ctx.grasp_class in cls_map:
            return float(cls_map[ctx.grasp_class])
        return float(profile.get("pick.p_fail")[ctx.clutter])
    if s in ("open", "close"):
        return float(profile.get(f"{s}.p_fail")[container_class(ctx.container_type)])
    return 0.0


def p_retry_success(profile, ctx: Ctx) -> float:
    s = ctx.skill
    if s == "pick":
        return float(profile.get("pick.p_retry_success"))
    if s in ("open", "close"):
        return float(profile.get(f"{s}.p_retry_success")[container_class(ctx.container_type)])
    return 1.0 - p_fail(profile, ctx)


def split_code(profile, skill: str, u: float) -> FailureCode:
    """Failure code from ``<skill>.split`` by inverse CDF over sorted keys."""
    split = profile.get(f"{skill}.split")
    acc = 0.0
    keys = sorted(split)
    for k in keys:
        acc += float(split[k])
        if u < acc:
            return FailureCode(k)
    return FailureCode(keys[-1])


def sample_outcome(profile, ctx: Ctx, u: list) -> Outcome:
    """Rules 2-4 of the failure model for a skill with a failure table (move, pick, open, close):
    failure (or retry success after a sticky failure), its code, then a silent failure."""
    if ctx.sticky and ctx.attempt >= 2:
        failed = u[U.FAIL] >= p_retry_success(profile, ctx)
    else:
        failed = u[U.FAIL] < p_fail(profile, ctx)
    if failed:
        return Outcome("fail", split_code(profile, ctx.skill, u[U.SPLIT]), "skill_fail")
    if ctx.skill in ("pick", "place", "put_in", "open") and u[U.SILENT] < float(profile.get("verify.p_false_success")):
        return Outcome("silent_fail", None, {"pick": "slip", "place": "fall", "put_in": "fall",
                                              "open": "partial_open"}[ctx.skill])
    return Outcome("ok")
