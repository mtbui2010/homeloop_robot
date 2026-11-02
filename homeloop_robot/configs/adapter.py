"""RobotAdapter of the homeloop mock robot: how robot_agent's planner drives it (docs/robot_agent.md).

robot_agent finds it with ``robot_agent.contract.load_adapter('homeloop_robot')``, which calls
``make_adapter()``. This is the only module of homeloop_robot that imports robot_agent.

  * manifest / geometry / i18n -- from manifest.yaml
  * bind()    -- an abstract plan step -> (skill name, params); names resolved on the robot's world
  * observe() / reconcile() / health() / pose() / container_states() -- the robot's own sensed state
"""

from __future__ import annotations

import re
from pathlib import Path

from robot_agent.contract import Geometry, Manifest, Messages, Observation, Unbindable

from .backend import get_backend

MANIFEST_PATH = Path(__file__).with_name("manifest.yaml")

TEXT_ACTIONS = {"Say", "Ask", "Announce", "Query"}
OBJECT_ACTIONS = {"Find", "Pick"}
PLACE_ACTIONS = {"MoveTo", "Place", "PutIn", "Open", "Close"}
DOCK_NAMES = {"dock", "charger", "home", "charging dock", "charging station", "base"}

PHRASES: dict = {
    "cannot_do": {"en": "I can't do that. I can move, find, pick up, put down, open and close things, "
                        "hand things over, talk and ask.",
                  "ko": "그 일은 할 수 없어요. 이동, 찾기, 집기, 놓기, 열고 닫기, 건네주기, 말하기, 질문은 할 수 있어요."},
    "done": {"en": "Done.", "ko": "다 했어요."},
    "which_one": {"en": "Which one do you mean?", "ko": "어느 것을 말씀하시는 거예요?"},
}


def to_name(name: str) -> str:
    """'KitchenCounter' / 'kitchen_counter' -> 'kitchen counter'; ids (with @ or _N) are kept."""
    s = str(name or "").strip()
    if not s or "@" in s or re.search(r"_\d+$", s):
        return s
    return " ".join(re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s).replace("_", " ").split()).lower()


class Adapter:
    quiet_skills = {"say", "ask", "announce", "wait"}

    def __init__(self, manifest: Manifest | None = None):
        self.manifest = manifest or Manifest.from_yaml(MANIFEST_PATH)
        self.geometry = Geometry.from_dict(self.manifest.geometry)
        self.i18n = Messages(language=self.manifest.language, phrases=PHRASES)

    # ── binding ─────────────────────────────────────────────────────────────────────────────────────
    def _world(self):
        return getattr(get_backend(), "world", None)

    def _resolve(self, name: str, kind: str) -> str:
        """A planner name -> an id of the robot's world when it names exactly one thing."""
        w = self._world()
        n = to_name(name)
        if w is None or not n:
            return n
        if kind == "place" and n.lower() in DOCK_NAMES:
            return w.house.dock
        order = {"object": (w.resolve_object,), "place": (w.resolve_place, w.resolve_person),
                 "person": (w.resolve_person,)}[kind]
        for f in order:
            r = f(n, None)
            if isinstance(r, str):
                return r
        return n

    def bind(self, step: dict, world=None):
        """{'action': 'Pick', 'object': 'Cup'} -> ('pick', {'inputs': 'cup_1'})."""
        action = (step.get("action") or "").strip()
        obj = str(step.get("object") or step.get("target") or step.get("inputs") or "").strip()
        spec = self.manifest.skill_for(action)
        if spec is None or spec.action in ("Observe", "Verify"):
            raise Unbindable(f"no skill for {action!r} on {self.manifest.robot} "
                             f"(it can {', '.join(sorted(self.plannable_actions))})")
        if spec.action == "Wait":
            return spec.name, {"inputs": obj or "5"}
        if spec.action in TEXT_ACTIONS:
            if not obj:
                raise Unbindable(f"{action} needs a sentence")
            params = {"inputs": obj}
            if step.get("lang"):
                params["lang"] = step["lang"]
            return spec.name, params
        if spec.action == "Dock":
            return spec.name, {"inputs": "dock"}
        if spec.action == "Look":
            return spec.name, {}
        if spec.action == "Handover":
            return spec.name, ({"inputs": self._resolve(obj, "person")} if obj else {})
        if not obj:
            raise Unbindable(f"{action} needs an argument")
        kind = "object" if spec.action in OBJECT_ACTIONS else "place"
        target = self._resolve(obj, kind)
        w = self._world()
        if kind == "place" and spec.action in ("MoveTo", "Place") and w is not None and target in w.people:
            # "near the person" (sage's on(obj -> person)): the support surface beside them that they can reach
            # from where they are now; with none, putting it "at the person" is a handover
            spot = person_spot(w, target)
            if spot is not None:
                return spec.name, {"inputs": spot}
            if spec.action == "Place":
                hand = self.manifest.skill_for("Handover")
                if hand is not None:
                    return hand.name, {"inputs": target}
        return spec.name, {"inputs": target}

    @property
    def plannable_actions(self) -> set:
        return {s.action for s in self.manifest.skills if s.action not in ("Observe", "Verify")}

    # ── state ───────────────────────────────────────────────────────────────────────────────────────
    def _observe(self) -> dict:
        b = get_backend()
        try:
            return b.observe()
        except Exception:                               # noqa: BLE001 - observe never raises
            return {}

    def observe(self, node=None) -> Observation:
        b = get_backend()
        o = self._observe()
        bel = getattr(b, "believed", {}) or {}
        held = bel.get("holding")
        at = o.get("at")
        return Observation(text=f"at {at or 'between places'}; holding {held or 'nothing'}",
                           visible=[], pose=list(o.get("pose_est") or []) or None, arrived=at,
                           hands={"right": held}, opened=set(bel.get("opened") or []),
                           sensor_health=self.health(node))

    def reconcile(self, world, node=None):
        b = get_backend()
        o = self._observe()
        bel = getattr(b, "believed", {}) or {}
        for attr, val in (("arrived", o.get("at")), ("holding", bel.get("holding"))):
            try:
                setattr(world, attr, val)
            except AttributeError:
                pass
        try:
            opened = getattr(world, "opened", None)
            if isinstance(opened, set):
                opened.clear()
                opened.update(bel.get("opened") or [])
        except AttributeError:
            pass
        return world

    def pose(self, node=None) -> dict:
        p = self._observe().get("pose_est")
        if not p:
            return {}
        return {"x": float(p[0]), "y": float(p[1]), "yaw": float(p[2]), "age_s": 0.0}

    def container_states(self, node=None) -> dict:
        """Open / closed of the container the robot stands at (what its camera reads); None for others."""
        w = self._world()
        if w is None:
            return {}
        here = w.robot.at
        out = {}
        for pid, p in sorted(w.house.places.items()):
            if p.kind == "container":
                out[pid] = (pid in w.opened) if pid == here else None
        return out

    def health(self, node=None) -> dict:
        b = get_backend()
        try:
            return b.health()
        except Exception:                               # noqa: BLE001
            return {"ok": None}


def person_spot(world, pid: str):
    """The nearest support surface with room that person ``pid`` can reach from where they are now
    (homeloop_robot.reach), or None."""
    from ..reach import reachable_surfaces
    spots = reachable_surfaces(world, pid, free_only=True)
    return spots[0] if spots else None


def make_adapter() -> Adapter:
    return Adapter()
