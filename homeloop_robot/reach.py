"""What a person can reach: support surfaces, posture, the delivery predicate (docs/reach.md).

A "bring me X" task is done when the object is in the person's hand, or (``mode=reach``) when it rests on a
support surface the person can reach from where they are at the end of the episode:

* a support surface is a place of kind ``surface`` whose type is a table, desk, counter, nightstand or shelf
  (never a seat, a bed, the floor, a stove, a sink or a drying rack);
* the person's posture is ``seated`` (at a seat place, a bed included: sitting up in bed) or ``standing``
  (anywhere else, and always while walking);
* reachable = horizontal distance from the body centre to the object's spot on the surface (``surface_xy``)
  <= R(posture) and the surface height within the posture's band.

R and the bands come from the ``reach.*`` profile parameters (profiles/real/reach.yaml, sources in
docs/calibration.md): R = forward grip reach - shoulder-to-body-centre offset + lean beyond the arm. They are
geometry, role ``nominal``, so ``ideal`` / ``real`` / ``stress`` share them.

Everything here reads only what a robot can observe (the house geometry, where the person is, whether they are
walking, the house profile's ``prefers_handover`` flag and the words of the request); never a task label.
"""

from __future__ import annotations

import functools
import math
import re
from dataclasses import dataclass
from typing import Optional

from .catalog import place_category

SUPPORT_TYPES = ("table", "desk", "counter", "nightstand", "shelf")
# receptacle category -> surface type (the world model's type of a support surface)
_TYPE_OF_CATEGORY = {
    "DiningTable": "table", "CoffeeTable": "table", "SideTable": "table", "Desk": "desk",
    "CounterTop": "counter", "Shelf": "shelf", "TVStand": "tv_stand", "StoveBurner": "stove", "Sink": "sink",
    "SinkBasin": "sink", "DryingRack": "rack", "Sofa": "seat", "ArmChair": "seat", "Chair": "seat", "Bed": "bed",
    "Floor": "floor", "Dock": "dock", "Stand": "stand",
}
TOP_OFFSET_M = 0.5            # default object spot: this far ahead of the approach pose (same as a seat's body)
SEAT_SNAP_M = 0.35            # a person within this of a seat's body position sits there
NEARBY_M = 2.0                # person_view lists furniture within this distance of the person
PARAMS = ("reach.grip_reach_m", "reach.body_offset_m", "reach.lean_seated_m", "reach.lean_standing_m",
          "reach.lean_standing_frail_m", "reach.band_seated_m", "reach.band_standing_m")

MODES = ("reach", "hand")
MODE_REASONS = (None, "explicit", "no_surface", "user_needs")


# ── parameters ────────────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ReachParams:
    grip_reach_m: float
    body_offset_m: float
    lean_seated_m: float
    lean_standing_m: float
    lean_standing_frail_m: float
    band_seated_m: tuple
    band_standing_m: tuple

    @classmethod
    def from_profile(cls, profile) -> "ReachParams":
        g = profile.get
        return cls(grip_reach_m=float(g("reach.grip_reach_m")), body_offset_m=float(g("reach.body_offset_m")),
                   lean_seated_m=float(g("reach.lean_seated_m")), lean_standing_m=float(g("reach.lean_standing_m")),
                   lean_standing_frail_m=float(g("reach.lean_standing_frail_m")),
                   band_seated_m=tuple(float(x) for x in g("reach.band_seated_m")),
                   band_standing_m=tuple(float(x) for x in g("reach.band_standing_m")))

    def radius(self, posture: str, frail: bool = False) -> float:
        if posture == "seated":
            lean = self.lean_seated_m
        else:
            lean = self.lean_standing_frail_m if frail else self.lean_standing_m
        return self.grip_reach_m - self.body_offset_m + lean

    def band(self, posture: str) -> tuple:
        return self.band_seated_m if posture == "seated" else self.band_standing_m


@functools.lru_cache(maxsize=1)
def default_params() -> ReachParams:
    """The ``real`` profile's reach parameters (identical in every profile: role nominal)."""
    from .profiles import load_profile
    return ReachParams.from_profile(load_profile("real"))


# ── surfaces ──────────────────────────────────────────────────────────────────────────────────────────

def surface_type(place) -> str:
    """table | desk | counter | nightstand | shelf (support types) or tv_stand | stove | sink | rack | seat | bed |
    floor | dock | stand | container."""
    if place.kind == "container":
        return "container"
    if place.kind in ("floor", "dock", "stand"):
        return place.kind
    if place.id.split("@", 1)[0] in ("nightstand", "bedside_table"):
        return "nightstand"
    return _TYPE_OF_CATEGORY.get(place_category(place), "other")


def is_support(place) -> bool:
    return place.kind == "surface" and surface_type(place) in SUPPORT_TYPES


def surface_xy(place) -> tuple:
    """Where the robot sets an object down on ``place``: its ``top`` in the house YAML, else 0.5 m ahead of the
    approach pose along the approach yaw."""
    if place.top is not None:
        return tuple(place.top)
    yaw = math.radians(place.yaw_deg)
    return (place.pos[0] + TOP_OFFSET_M * math.cos(yaw), place.pos[1] + TOP_OFFSET_M * math.sin(yaw))


# ── people ────────────────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PersonPose:
    id: str
    pos: tuple
    posture: str                     # seated | standing
    place: Optional[str]             # the seat / stand spot the person is at (None while walking or elsewhere)
    room: Optional[str]
    moving: bool

    def to_json(self) -> dict:
        return {"id": self.id, "pos": [round(self.pos[0], 6), round(self.pos[1], 6)], "posture": self.posture,
                "place": self.place, "room": self.room, "moving": self.moving}


def body_xy(world, place_id: str) -> Optional[tuple]:
    pl = world.house.places.get(place_id)
    if pl is None:
        return None
    if pl.person_pos is not None:
        return tuple(pl.person_pos)
    yaw = math.radians(pl.yaw_deg)
    return (pl.pos[0] + TOP_OFFSET_M * math.cos(yaw), pl.pos[1] + TOP_OFFSET_M * math.sin(yaw))


def person_pose(world, pid: str, pos=None, moving: Optional[bool] = None) -> PersonPose:
    """Posture and place of person ``pid`` at ``pos`` (default: where they are now, ``world.people_now``).
    Seated when not walking and within 0.35 m of a seat's body position (a bed counts: sitting up in bed; their
    own usual place counts at their start position, a desk / table included); standing otherwise (a stand
    spot, or anywhere else)."""
    person = world.people[pid]
    xy = tuple(pos) if pos is not None else world.person_xy(pid)
    mv = world.person_moving(pid) if moving is None else bool(moving)
    room = world.room_of(xy)
    if not mv:
        best = None
        cands = []
        if math.dist(xy, tuple(person.pos)) <= SEAT_SNAP_M and person.seat in world.house.places:
            cands.append((math.dist(xy, tuple(person.pos)), person.seat))
        for plid, pl in sorted(world.house.places.items()):
            if pl.kind not in ("seat", "stand"):
                continue
            b = body_xy(world, plid)
            if b is not None and math.dist(xy, b) <= SEAT_SNAP_M:
                cands.append((math.dist(xy, b), plid))
        if cands:
            best = sorted(cands)[0][1]
        if best is not None:
            kind = world.house.places[best].kind
            # a person whose usual place is a desk / table sits at it (the chair is not a place of its own)
            seated = kind == "seat" or (best == person.seat and kind == "surface")
            return PersonPose(pid, xy, "seated" if seated else "standing", best, room, False)
    return PersonPose(pid, xy, "standing", None, room, mv)


# ── reach ─────────────────────────────────────────────────────────────────────────────────────────────

def place_reachable(world, place_id: str, pid: str, pose: Optional[PersonPose] = None,
                    params: Optional[ReachParams] = None) -> bool:
    """Is support surface ``place_id`` within reach of person ``pid`` (pose: now)?"""
    pl = world.house.places.get(place_id)
    if pl is None or not is_support(pl):
        return False
    pose = pose or person_pose(world, pid)
    prm = params or default_params()
    if pose.room is None or pl.room not in world.rooms_of(pose.pos):
        return False
    lo, hi = prm.band(pose.posture)
    if not (lo - 1e-9 <= pl.height_m <= hi + 1e-9):
        return False
    r = prm.radius(pose.posture, bool(getattr(world.people[pid], "frail", False)))
    return math.dist(surface_xy(pl), pose.pos) <= r + 1e-9


def reachable_surfaces(world, pid: str, pose: Optional[PersonPose] = None, params: Optional[ReachParams] = None,
                       free_only: bool = False) -> list:
    """Support surfaces person ``pid`` can reach, nearest first (ties by id)."""
    pose = pose or person_pose(world, pid)
    out = []
    for plid, pl in sorted(world.house.places.items()):
        if not place_reachable(world, plid, pid, pose, params):
            continue
        if free_only and world.free_slots(plid) <= 0:
            continue
        out.append((math.dist(surface_xy(pl), pose.pos), plid))
    return [p for _, p in sorted(out)]


def reachable(obj: str, person: str, world, pose: Optional[PersonPose] = None,
              params: Optional[ReachParams] = None) -> bool:
    """Can ``person`` take ``obj`` without getting up: it is in their hand, or it rests on a support surface
    within their reach."""
    o = world.objects.get(obj)
    if o is None or person not in world.people:
        return False
    if o.at == f"person:{person}":
        return True
    if o.inside or o.at not in world.house.places:
        return False
    return place_reachable(world, o.at, person, pose, params)


def delivered(world, obj: str, person: str, mode: str, pose: Optional[PersonPose] = None,
              params: Optional[ReachParams] = None) -> bool:
    """The delivery goal: ``hand`` = handed over (the object is in the person's hand); ``reach`` = handed over
    or on a reachable support surface, judged where the person is now (the end of the episode)."""
    o = world.objects.get(obj)
    if o is None or person not in world.people:
        return False
    if o.at == f"person:{person}":
        return True
    if mode == "hand":
        return False
    if mode != "reach":
        raise ValueError(f"delivery mode must be reach or hand, not {mode!r}")
    return reachable(obj, person, world, pose, params)


# ── what the robot observes, and the mode it chooses ─────────────────────────────────────────────────

def person_view(world, pid: str, pose: Optional[PersonPose] = None, radius_m: float = NEARBY_M) -> dict:
    """What a robot sees of a person: posture, place, room, walking or not, the house profile's
    ``prefers_handover`` and the furniture within ``radius_m`` (type, height, distance, free room). No reach
    verdict and no task label: a planner decides from this."""
    pose = pose or person_pose(world, pid)
    near = []
    for plid, pl in sorted(world.house.places.items()):
        if pl.kind in ("floor", "dock", "stand") or pl.room not in world.rooms_of(pose.pos):
            continue
        xy = surface_xy(pl) if pl.kind == "surface" else (body_xy(world, plid) if pl.kind == "seat" else tuple(pl.pos))
        d = math.dist(xy, pose.pos)
        if d > radius_m:
            continue
        near.append({"place": plid, "type": surface_type(pl), "height_m": round(pl.height_m, 3),
                     "dist_m": round(d, 2), "free": max(0, world.free_slots(plid)) if pl.kind != "seat" else None})
    near.sort(key=lambda x: (x["dist_m"], x["place"]))
    v = pose.to_json()
    v.update({"prefers_handover": bool(getattr(world.people[pid], "prefers_handover", False)), "nearby": near})
    return v


_HAND_EN = re.compile(r"\b(hand|hands|handed)\b(?!\s+(cream|lotion|towel|towels|soap|sanitizer|sanitiser|wash|"
                      r"mirror|bag|truck|brake|written|made|held))", re.I)
_HAND_EN_NOT = re.compile(r"\b(on the other hand|second[- ]hand|hand[- ]in[- ]hand|by hand|first[- ]hand|"
                          r"hand[- ]me[- ]down)\b", re.I)
_HAND_KO = re.compile(r"(건네|손에|손으로|손 위에|손바닥)")


def wording_wants_hand(text: str, lang: str) -> bool:
    """Does the request ask for a handover in so many words? EN: "hand me", "hand it to", "put it in my
    hand(s)" (not "hand cream", "hand towel", "by hand", ...); KO: 건네-, 손에, 손으로."""
    t = str(text or "")
    if lang == "ko":
        return bool(_HAND_KO.search(t))
    t2 = _HAND_EN_NOT.sub(" ", t)
    return bool(_HAND_EN.search(t2))


@dataclass(frozen=True)
class ModeChoice:
    mode: str                        # reach | hand
    reason: Optional[str]            # None | explicit | user_needs | no_surface
    surface: Optional[str]           # the surface to put it on (mode reach)


def choose_mode(world, pid: str, text: str = "", lang: str = "en", pose: Optional[PersonPose] = None,
                params: Optional[ReachParams] = None) -> ModeChoice:
    """How to deliver to ``pid`` from what a robot observes: the words ask for the hand -> hand (explicit);
    the house profile says the person needs a handover -> hand (user_needs); no reachable support surface with
    room -> hand (no_surface); else reach, on the nearest reachable support surface."""
    if wording_wants_hand(text, lang):
        return ModeChoice("hand", "explicit", None)
    if getattr(world.people[pid], "prefers_handover", False):
        return ModeChoice("hand", "user_needs", None)
    s = reachable_surfaces(world, pid, pose, params, free_only=True)
    if not s:
        return ModeChoice("hand", "no_surface", None)
    return ModeChoice("reach", None, s[0])
