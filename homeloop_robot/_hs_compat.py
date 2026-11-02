"""Shared helpers for the user, ASR, dialog, safety and hazard modules.

The robot core defines the protocol dataclasses (``types.py``) and the seeded random streams (``rng.py``).
This module imports them from there. When the core modules are not present (the user/safety stream is built
and tested in parallel with the core), it falls back to local definitions with the same names and fields,
so both sides code against one definition (DESIGN section 13.1).
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from typing import Any

# --------------------------------------------------------------------------------------------- rng
try:  # pragma: no cover - exercised once the core lands
    from homeloop_robot.rng import Streams, derive_seed, r6, rng_for  # type: ignore
except ImportError:  # local fallback, identical contract (DESIGN 4.6)

    def derive_seed(*parts: Any) -> int:
        return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big")

    def rng_for(*parts: Any) -> random.Random:
        return random.Random(derive_seed(*parts))

    def r6(x: float) -> float:
        y = round(float(x), 6)
        return 0.0 if y == 0 else y

    class Streams:  # type: ignore[no-redef]
        def __init__(self, seed: int, key: str = ""):
            self.seed = seed
            self.key = key
            self._streams: dict[str, random.Random] = {}

        def stream(self, name: str) -> random.Random:
            if name not in self._streams:
                self._streams[name] = random.Random(derive_seed(self.seed, self.key, "stream", name))
            return self._streams[name]

        def rng_for(self, *parts: Any) -> random.Random:
            return random.Random(derive_seed(self.seed, self.key, *parts))


# ------------------------------------------------------------------------------------------- types
try:  # pragma: no cover
    from homeloop_robot.types import (  # type: ignore
        HazardEvent,
        Heard,
        PersonState,
        Traverse,
        UserEvent,
        UserReply,
        Violation,
    )
except ImportError:

    @dataclass(frozen=True)
    class UserReply:  # type: ignore[no-redef]
        text: str
        kind: str  # correct | wrong | not_sure | no_answer | yes | no
        latency_s: float
        heard_question: bool

    @dataclass(frozen=True)
    class Heard:  # type: ignore[no-redef]
        text: str
        event: str  # ok | not_heard | partial | corrupted

    @dataclass(frozen=True)
    class UserEvent:  # type: ignore[no-redef]
        t: float
        kind: str  # stop | correction
        text: str
        new_goal: dict | None

    @dataclass(frozen=True)
    class PersonState:  # type: ignore[no-redef]
        id: str
        pos: tuple[float, float]
        vel: tuple[float, float]
        room: str
        awake: bool

    @dataclass(frozen=True)
    class Violation:  # type: ignore[no-redef]
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
    class Traverse:  # type: ignore[no-redef]
        duration_s: float
        slow_s: float
        stopped_s: float
        aborted: bool
        min_sep_m: float | None
        violations: tuple = ()

    @dataclass(frozen=True)
    class HazardEvent:  # type: ignore[no-redef]
        t: float
        code: str
        skill: str
        args: dict
        why: str


# ---------------------------------------------------------------------------------------- profile
def param(profile: Any, name: str) -> Any:
    """Value of a profile parameter. Accepts the core ``Profile`` (``.get``) or a plain dict."""
    if isinstance(profile, dict):
        return profile[name]
    return profile.get(name)


# --------------------------------------------------------------------------------------- geometry
def dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def polyline_length(path) -> float:
    return sum(dist(path[i], path[i + 1]) for i in range(len(path) - 1))


def point_along(path, s: float) -> tuple[float, float]:
    """Point at arc length ``s`` along a polyline (clamped to its ends)."""
    if len(path) == 1 or s <= 0:
        return (float(path[0][0]), float(path[0][1]))
    acc = 0.0
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        seg = dist(a, b)
        if acc + seg >= s and seg > 0:
            f = (s - acc) / seg
            return (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]))
        acc += seg
    return (float(path[-1][0]), float(path[-1][1]))


def world_path(world: Any, a, b) -> list[tuple[float, float]]:
    """Walking path between two points: the world's door-aware path when available, else a straight line."""
    fn = getattr(world, "path", None)
    if fn is not None:
        try:
            p = fn(tuple(a), tuple(b))
            if p:
                return [tuple(map(float, q)) for q in p]
        except Exception:  # noqa: BLE001 - fall back to a straight line
            pass
    return [tuple(map(float, a)), tuple(map(float, b))]


def room_of(world: Any, xy) -> str | None:
    fn = getattr(world, "room_of", None)
    if fn is not None:
        return fn(tuple(xy))
    for rid, room in sorted(getattr(world.house, "rooms", {}).items()):
        x0, y0, x1, y1 = room.rect
        if x0 <= xy[0] <= x1 and y0 <= xy[1] <= y1:
            return rid
    return None


def rooms_at(world: Any, xy) -> set:
    """Rooms containing ``xy`` (a doorway point lies in both rooms)."""
    fn = getattr(world, "rooms_of", None)
    if fn is not None:
        return set(fn(tuple(xy)))
    r = room_of(world, xy)
    return {r} if r is not None else set()


def adjacent_rooms(world: Any, room: str | None) -> set:
    fn = getattr(world, "adjacent_rooms", None)
    if fn is not None and room is not None:
        return set(fn(room))
    out = set()
    for door in getattr(world.house, "doors", []) or []:
        a, b = door.rooms
        if a == room:
            out.add(b)
        elif b == room:
            out.add(a)
    return out


def places(world: Any) -> dict:
    return world.house.places


def age_lower(age_group: str | None) -> int | None:
    """Lower bound of an age group string such as ``"80-99"`` or ``"65+"``."""
    if not age_group:
        return None
    head = str(age_group).replace("+", "-").split("-")[0].strip()
    return int(head) if head.isdigit() else None


# ------------------------------------------------------------------------------------ consistency
Z_999 = 3.2905  # two-sided 99.9 % normal quantile


def binomial_row(name: str, expected: float, hits: int, n: int, context: str = "") -> dict:
    """A consistency row: the empirical rate must lie in the 99.9 % binomial interval of ``expected``."""
    obs = hits / n if n else 0.0
    half = Z_999 * math.sqrt(max(expected * (1 - expected), 0.0) / n) if n else 0.0
    lo, hi = max(0.0, expected - half), min(1.0, expected + half)
    if expected in (0.0, 1.0):
        ok = obs == expected
    else:
        ok = lo <= obs <= hi
    return {"param": name, "context": context, "expected": r6(expected), "observed": r6(obs), "n": n,
            "lo": r6(lo), "hi": r6(hi), "ok": bool(ok)}
