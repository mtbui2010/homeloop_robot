"""robot_agent ENV of a house: ``env_for(world)``; ``ENV`` for the default house (docs/robot_agent.md)."""

from __future__ import annotations

import math

from ..world import World, from_house
from .backend import DEFAULT_HOUSE


DOCK_TASK_WORDS = ["charge", "charging", "charging station", "충전", "충전기"]


PERSON_SPOT_RADIUS_M = 1.2   # Hall's personal zone, outer edge (WALTERS05 Table 1; docs/calibration.md)

# robot_agent's AssistLoop reads a goal place that normalises to one of these words as "the user, place
# unknown" (assist_loop._USER_WORDS) and asks where they are, so no ENV key may normalise to one of them. The copy
# is checked against robot_agent's own set by the bench test tests/test_reach_ra_bind.py.
RESERVED_USER_WORDS = frozenset({"me", "user", "here", "you", "myself", "person"})

# The ENV key of the person who gives the task. robot_agent reads a plan back with the ENV key itself ("I will put
# the mug on the {key}.", AssistLoop.summary), so a key is what the user hears: a raw id ('person_user',
# 'partner_b') must not be one (pilot round 1, hl-dev-000010 / 000013). The speaker is addressed as "you" (the
# read-back is said to them); "you" alone is a reserved user word, so the key names the robot's target the way a
# robot says it to the person: the support surface beside them (the entry's spot) or, with none, where they are.
# The key must not END in a word people say in a request: robot_agent also takes the last word of a multi-word ENV
# head as a place phrase (understand._phrases: 'coffee table' -> 'table'), so the earlier key "spot near you" made
# every "you" of an instruction ("Can you put ...") a mention of the speaker's spot (3947 of the 6000 dev / test EN
# instructions): "You mentioned the you. What should I do there?" and "(the you you mentioned is not in my plan)"
# (fresh pilot round 1, hl-dev-000057 / 000016 EN). "reach" is in no dev / test instruction
# (tests/test_person_keys.py; the bench's tests/test_person_key_mentions.py runs robot_agent's place_mentions on
# every dev / test instruction).
SPEAKER_KEY = "spot within your reach"

# robot_agent matches a non-ASCII place phrase as a plain substring (understand._find), so a one-syllable Korean
# person name (나, 저, 애, 딸) would be "mentioned" inside 하나, 저녁, 나간다고, 딸기 (pilot round 2, hl-dev-000013 KO:
# "You mentioned the 나"). Such a name goes into the ENV in the forms that name a person as a destination: the
# dative particles, and the contracted pronouns (나에게 -> 내게, 저에게 -> 제게).
KO_DATIVE = ("한테", "에게")
KO_CONTRACTED = {"나": ["내게"], "저": ["제게"]}


def env_alias_forms(alias: str) -> list:
    """The spellings of a person alias written to the ENV: itself, or, for a one-syllable non-ASCII name, its
    dative forms (it would otherwise match inside longer words)."""
    a = str(alias or "").strip()
    if not a or a.isascii() or len(a.replace(" ", "")) > 1:
        return [a] if a else []
    return [a + p for p in KO_DATIVE] + KO_CONTRACTED.get(a, [])


def _words(name) -> str:
    """robot_agent's name normaliser (assist_loop.words): '_' / '-' to spaces, camel case split, lower case."""
    import re
    s = str(name or "").replace("_", " ").replace("-", " ")
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    return " ".join(s.lower().split())


def _strip_article(w: str) -> str:
    for a in ("the ", "a ", "an ", "my ", "your "):
        if w.startswith(a):
            return w[len(a):].strip()
    return w


def _reserved(key: str) -> bool:
    w = _words(key)
    return w in RESERVED_USER_WORDS or _strip_article(w) in RESERVED_USER_WORDS


def person_keys(world) -> dict:
    """{person id: ENV key}: the speaker -> :data:`SPEAKER_KEY`; anyone else -> their English name as people say
    it, lower case, without the article ('husband', 'grandpa', 'kid', 'roommate b'). A name that is a reserved
    user word, a place key or another person's key falls back to the id ('person_<id>' when the id is reserved)."""
    uid = world.user_id() if hasattr(world, "user_id") else None
    taken = {_words(k) for k in world.house.places}
    out: dict = {}
    for pid in sorted(world.people):
        per = world.people[pid]
        k = SPEAKER_KEY if pid == uid else _strip_article(_words((per.name or {}).get("en", "")))
        if not k or _reserved(k) or _words(k) in taken:
            k = f"person_{pid}" if _reserved(pid) else pid
        taken.add(_words(k))
        out[pid] = k
    return out


def person_key(world, pid: str) -> str:
    """The ENV key of person ``pid`` of ``world`` (:func:`person_keys`)."""
    return person_keys(world).get(pid, pid)


def standoff_m() -> float:
    """move.person_standoff_m of the real profile (the same nominal value in every profile)."""
    from ..profiles import load_profile
    return float(load_profile("real").get("move.person_standoff_m"))


def person_target(env: dict, key: str, world=None):
    """(person id, spot place id or None) when ENV key ``key`` (or a person id / name of ``world``) names a
    person, else None. The spot is the one the ENV entry was built with, so a MoveTo / Place of the person goes
    where the ENV loc says."""
    e = (env or {}).get(key)
    if isinstance(e, dict) and e.get("person"):
        return e["person"], e.get("spot")
    if world is not None and key and world.resolve_place(key, None) is None:
        pid = world.resolve_person(key, None)
        if isinstance(pid, str):
            e = (env or {}).get(person_key(world, pid))
            if isinstance(e, dict) and e.get("person") == pid:
                return pid, e.get("spot")
            return pid, person_spot(world, pid)
    return None


def person_spot(world, pid: str, radius_m: float = PERSON_SPOT_RADIUS_M):
    """Where "near person ``pid``" is for a robot that sees the room: the nearest support surface (table, desk,
    counter, nightstand, shelf) in the person's room whose set-down spot is within ``radius_m`` of where they are
    now and that has free room, or None. Chosen from the same scene facts every planner observes (people_now and
    the nearby furniture); it does NOT use the judge's reach radius, height bands or posture, so the surface may
    still be out of the person's reach, and then the delivery fails like anyone's would."""
    from ..reach import is_support, surface_xy
    xy = world.person_xy(pid)
    rooms = world.rooms_of(xy)
    best = []
    for plid, pl in sorted(world.house.places.items()):
        if not is_support(pl) or pl.room not in rooms or world.free_slots(plid) <= 0:
            continue
        d = math.dist(surface_xy(pl), xy)
        if d <= radius_m + 1e-9:
            best.append((d, plid))
    return sorted(best)[0][1] if best else None


def person_loc(world, pid: str, spot) -> tuple:
    """(ENV loc, height) of person ``pid``'s entry: the support surface ``spot`` beside them, or, with none, where a
    move to the person stops (skills.person_stop_xy, the robot's own rule)."""
    from ..skills import person_stop_xy
    if spot is not None:
        p = world.house.places[spot]
        return {"x": float(p.pos[0]), "y": float(p.pos[1]), "rz": float(p.yaw_deg)}, float(p.height_m)
    xy = world.person_xy(pid)
    sx, sy = person_stop_xy(world, xy, standoff_m())
    return {"x": float(sx), "y": float(sy), "rz": float(math.degrees(math.atan2(xy[1] - sy, xy[0] - sx)))}, 0.0


def refresh_person_spot(env: dict, pid: str, world):
    """The spot of person ``pid``'s ENV entry, looked at again in ``world`` (the scene now) when the entry's spot is
    no longer usable: there was none (every surface beside the person was full when the ENV was built) or it has no
    free room now. Then the entry gets the free support surface beside the person now (:func:`person_spot`), or the
    stop point when there is none, IN PLACE: robot_agent's copies of the ENV share the entry dicts, so its arrival
    check measures the move against the new loc. A usable spot is kept. Gate pilot round 1, hl-dev-000008: the
    nightstand beside grandma held the blue book the task moves, so her entry had no spot, and the water bottle could
    not be put down beside her after the book was gone ("a person, use handover"). Returns the spot (None: none)."""
    e = next((v for _k, v in sorted((env or {}).items()) if isinstance(v, dict) and v.get("person") == pid), None)
    if e is None:
        return person_spot(world, pid)
    old = e.get("spot")
    if old is not None and old in world.house.places and world.free_slots(old) > 0:
        return old
    new = person_spot(world, pid)
    if new == old:
        return old
    e["loc"], e["height"] = person_loc(world, pid, new)
    e["spot"] = new
    return new


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
    # on(mug -> grandma)); the entry stands at the free support surface nearest to the person within Hall's
    # personal zone (person_spot, geometry only) and records it as ``spot``; with none, it stands where a move to
    # the person stops (skills.person_stop_xy, the robot's own rule). ra_skills.move / place of the entry go to
    # the spot (or to the person), so the robot ends at the ENV loc and robot_agent's arrival check holds.
    keys = person_keys(world)
    for pid, per in sorted(world.people.items()):
        key = keys[pid]
        if key in env:
            continue
        spot = person_spot(world, pid)
        loc, height = person_loc(world, pid, spot)
        aliases, seen = [], set()
        for a in [f for n in [per.name.get("en", ""), per.name.get("ko", "")] + list(per.aliases.get("en") or []) +
                  list(per.aliases.get("ko") or []) + ([key.replace("_", " ")] if key != pid else [])
                  for f in env_alias_forms(n)]:
            if a and a not in seen:
                seen.add(a)
                aliases.append(a)
        env[key] = {"loc": loc, "height": height, "default_mode": "front", "aliases": aliases, "openable": False,
                    "person": pid, "spot": spot}
    return env


ENV = env_for(from_house(DEFAULT_HOUSE, 0))
