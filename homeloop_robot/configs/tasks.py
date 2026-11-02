"""robot_agent ENV of a house: ``env_for(world)``; ``ENV`` for the default house (docs/robot_agent.md)."""

from __future__ import annotations

from ..world import World, from_house
from .backend import DEFAULT_HOUSE


def env_for(world: World) -> dict:
    """Per place: {loc: {x, y, rz}, height, default_mode, aliases, openable} keyed by place id."""
    env = {}
    for pid, p in sorted(world.house.places.items()):
        room = world.house.rooms[p.room]
        rname, pname = room.name.get("en", ""), p.name.get("en", "")
        with_room = pname if pname.lower().startswith(rname.lower()) else f"{rname} {pname}".strip()
        aliases = [p.name.get("en", ""), p.name.get("ko", "")] + list(p.aliases.get("en") or []) + \
            list(p.aliases.get("ko") or []) + [with_room]
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
    return env


ENV = env_for(from_house(DEFAULT_HOUSE, 0))
