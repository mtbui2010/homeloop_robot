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
from .tasks import person_key, person_keys, person_spot  # noqa: F401  (re-exported: adapter.person_spot)

MANIFEST_PATH = Path(__file__).with_name("manifest.yaml")

TEXT_ACTIONS = {"Say", "Ask", "Announce", "Query"}
OBJECT_ACTIONS = {"Find", "Pick"}
PLACE_ACTIONS = {"MoveTo", "Place", "PutIn", "Open", "Close"}
DOCK_NAMES = {"dock", "charger", "home", "charging dock", "charging station", "base"}

# robot_agent's Announcer speaks the plan milestones (task start, step start / success / fail, done) from the robot's
# i18n, falling back to its core table, which has English and Vietnamese only: without these a Korean user heard
# "Task completed" / "Task failed" (pilot rounds 1-4, KO hl-dev-000013 / 000001). Plain polite Korean (해요체/합니다체);
# {object} {verb} {reason} {eul} (을/를) are filled by the Announcer.
_KO_MILESTONES = {
    "task_start": "작업을 시작합니다",
    "step_start": "{object} {verb}{eul} 진행합니다",
    "step_success": "{object} {verb}{eul} 완료했습니다",
    "step_fail": "{object} {verb}에 실패했습니다. {reason}",
    "replan": "계획을 다시 세웁니다",
    "done_success": "작업을 완료했습니다",
    "done_fail": "작업에 실패했습니다",
    "plan_ready": "계획을 생성했습니다",
    "unsupported": "지원하지 않는 동작입니다",
    "llm_down": "지금 언어 모델에 연결할 수 없어서 작업을 중단합니다",
    "generic": "진행 중입니다",
}

# per-action verbs: the manifest's actions and the skill names of robot_agent's direct path ("find::apple")
_KO_VERBS = {
    "MoveTo": "이동", "GoTo": "이동", "Navigate": "이동",
    "Find": "찾기", "Search": "찾기", "Detect": "찾기", "Look": "둘러보기",
    "Pick": "집기", "PickUp": "집기", "Grasp": "집기",
    "Place": "놓기", "PlaceAt": "놓기", "PutDown": "놓기", "PutIn": "넣기",
    "Open": "열기", "Close": "닫기", "Handover": "건네주기", "Dock": "충전",
    "navigate": "이동", "move": "이동", "moveto": "이동",
    "find": "찾기", "detect": "찾기", "detect_object": "찾기", "look": "둘러보기",
    "pick": "집기", "grasp": "집기",
    "place": "놓기", "put": "놓기", "put_in": "넣기",
    "open": "열기", "close": "닫기", "handover": "건네주기", "dock": "충전",
}

PHRASES: dict = {
    **{k: {"ko": v} for k, v in _KO_MILESTONES.items()},
    **{f"verb.{a}": {"ko": v} for a, v in _KO_VERBS.items()},
    "cannot_do":{"en": "I can't do that. I can move, find, pick up, put down, open and close things, "
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
        if kind in ("place", "person"):
            pid = self._person_of_key(str(name or "").strip())
            if pid is not None:
                return pid
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

    def _person_of_key(self, key: str):
        """The person id of an ENV person key ('spot near you' -> 'user', 'husband' -> 'partner_b'), else None."""
        w = self._world()
        if w is None:
            return None
        for pid, k in sorted(person_keys(w).items()):
            if k != pid and key in (k, k.replace("_", " ")):
                return pid
        return None

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
            # "near the person" (sage's on(obj -> person)): the nearest free support surface the robot sees beside
            # them (adapter.person_spot: geometry only, not the judge's reach test). With none, the step stays
            # aimed at the person: MoveTo drives to them, Place fails ("a person, use handover"); the adapter never
            # turns a Place into a handover (that is the planner's choice)
            # the ENV entry's spot (env_for of the start world), the one ra_skills.move / place use for the raw
            # ENV key robot_agent's AssistLoop passes
            from .ra_skills import _person
            per = _person(person_key(w, target))
            spot = per[1] if per is not None else person_spot(w, target)
            if spot is not None:
                return spec.name, {"inputs": spot}
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


def make_adapter() -> Adapter:
    return Adapter()
