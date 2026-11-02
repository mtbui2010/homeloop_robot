"""robot_agent ENV of a house: ``env_for(world)``; ``ENV`` for the default house (docs/robot_agent.md)."""

from __future__ import annotations

from ..world import World, from_house
from .backend import DEFAULT_HOUSE


DOCK_TASK_WORDS = ["charge", "charging", "charging station", "충전", "충전기"]


def env_for(world: World) -> dict:
    """Per place: {loc: {x, y, rz}, height, default_mode, aliases, openable} keyed by place id."""
    env = {}
    for pid, p in sorted(world.house.places.items()):
        room = world.house.rooms[p.room]
        rname, pname = room.name.get("en", ""), p.name.get("en", "")
        with_room = pname if rname.lower() in pname.lower() else f"{rname} {pname}".strip()
        aliases = [p.name.get("en", ""), p.name.get("ko", "")] + list(p.aliases.get("en") or []) + \
            list(p.aliases.get("ko") or []) + [with_room]
        if pid == world.house.dock:
            # how people name the charger in a task: "go back and charge", "충전하러 가"
            aliases += DOCK_TASK_WORDS
        if "_" in pid:
            # robot_agent reads a copied key through its word normalizer ('bath_cabinet@bathroom' ->
            # 'bath cabinet@bathroom'); this spelling resolves it back to the key instead of to the whole room
            aliases.append(pid.replace("_", " "))
        seen, al = set(), []
        for a in aliases:
            if a and a not in seen:
                seen.add(a)
                al.append(a)
        env[pid] = {"loc": {"x": float(p.pos[0]), "y": float(p.pos[1]), "rz": float(p.yaw_deg)},
                    "height": float(p.height_m), "default_mode": "front", "aliases": al,
                    "openable": bool(p.container and p.container.openable)}
    # people: robot_agent's planners name a person as the place to bring something to ("bring me the mug" ->
    # on(mug -> grandma)); the entry stands at the support surface the person can reach (adapter.person_spot), or
    # at the person when there is none. The adapter binds MoveTo / Place of a person the same way.
    from ..reach import reachable_surfaces
    for pid, per in sorted(world.people.items()):
        if pid in env:
            continue
        spots = reachable_surfaces(world, pid, free_only=True)
        if spots:
            p = world.house.places[spots[0]]
            loc, height = {"x": float(p.pos[0]), "y": float(p.pos[1]), "rz": float(p.yaw_deg)}, float(p.height_m)
        else:
            xy = world.person_xy(pid)
            loc, height = {"x": float(xy[0]), "y": float(xy[1]), "rz": 0.0}, 0.0
        aliases, seen = [], set()
        for a in [per.name.get("en", ""), per.name.get("ko", "")] + list(per.aliases.get("en") or []) + \
                list(per.aliases.get("ko") or []):
            if a and a not in seen:
                seen.add(a)
                aliases.append(a)
        env[pid] = {"loc": loc, "height": height, "default_mode": "front", "aliases": aliases, "openable": False}
    return env


ENV = env_for(from_house(DEFAULT_HOUSE, 0))
