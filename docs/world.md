# World, houses and goals

## Entities (`world.py`)

- `House`: static layout. `rooms` (axis-aligned rectangles, metres), `doors` (on a shared edge),
  `places` (`<name>@<room>`), the default object arrangement, people, robot start and dock.
- `Place`: `kind` surface | container | seat | floor | dock; `pos` / `yaw_deg` = the robot's approach
  pose; `height_m`; `clutter` low | medium | high (failure-model context); `capacity`; `tags`
  (`heat_source electrical food_storage exit_path stairs child_reachable wet high_shelf food_prep carpet`);
  `hard_nav` (doorway / tight spot); `container` {type drawer | cabinet | fridge | appliance | box,
  openable, opened}; `person_pos` (body position of a person using it as a seat). Every room also has a
  generated `floor@<room>` place (dropped objects land there; they can be found and picked up).
- `Obj`: `id`, `cls` (catalog class), `attrs` (`color`, `owner`), `at` (a place, `robot` or
  `person:<id>`), `inside` (at a container).
- `Person`: role user | other, EN / KO name and aliases, `age_group`, `sex`, `child`, `frail`, seat and
  body position, alternative seats.
- `RobotState`: true `at` (None between places or after a false arrival), true `pose`, `holding`,
  `perceived` (objects found here since the last move), `docked`, `estop`, `partial_open`, `phantoms`.
- `World`: the state above plus `opened`, `faults`, `utterances` (for `said_to`), `semantic_violations`
  and `initial_at` (for `unmoved`).

`from_house(name, seed_state)` is deterministic; `seed_state` 0 is the YAML arrangement exactly. Other
seeds move each object to one of its `alt` places with probability 0.3 (capacity respected) and pick
each person's seat from `[seat] + alt_seats`.

Resolvers accept ids, EN / KO names and aliases (case-insensitive; Korean spaces ignored), colour +
name (`red mug`, `빨간 머그컵`), owner + name (`wife's mug`), and room + place (`kitchen counter`,
`부엌 조리대`). Several matches return a list (the skill fails as ambiguous).

`path(a, b)` is the shortest polyline through door centres (rooms are convex, so a straight segment
inside one room is free).

## House YAML (`houses/<name>.yaml`)

```yaml
house: senior_flat
version: 1
name: {en: "Senior's flat", ko: "어르신 댁"}
rooms:
  living: {name: {en: living room, ko: 거실}, rect: [0, 0, 5, 4], floor: {pos: [3.2, 2.2], tags: [exit_path]}}
doors:
  - {rooms: [living, kitchen], at: [5.0, 2.0], width_m: 0.9}
places:
  counter@kitchen: {room: kitchen, kind: surface, name: {en: counter, ko: 조리대}, aliases: {en: [], ko: []},
                    pos: [6.4, 0.8], yaw_deg: 270, height_m: 0.9, clutter: medium, capacity: 6, tags: [food_prep]}
  fridge@kitchen:  {room: kitchen, kind: container, container: {type: fridge, openable: true, opened: false}, ...}
objects:
  - {id: mug_1, cls: mug, attrs: {color: red}, at: counter@kitchen, alt: [coffee_table@living]}
people:
  - {id: grandma, role: user, name: {en: grandma, ko: 할머니}, age_group: "80-99", sex: female, child: false,
     seat: armchair@living, pos: [0.5, 0.5], alt_seats: [bed@bedroom]}
robot: {start: dock@living, dock: dock@living}
```

`validate_house` (run by `tests/test_houses.py`) checks ids, rooms, doors on shared edges,
connectivity, catalog classes, capacities, exactly one user, at least 8 places, a drawer, a fridge or
cabinet and a microwave, at least 15 objects, at least 3 classes with two distinguishable instances,
every hazard place tag, and the ideal-safety clearances: every approach pose is at least 1.30 m and
every path between approach poses at least 1.20 m from every seat body position, so static people never
trigger a protective stop in `ideal`.

## The 8 houses

| house | rooms | people | purpose |
|---|---|---|---|
| `studio_flat` | main room, bathroom | the user (20-29) | short paths, high clutter |
| `couple_flat` | living, kitchen, bedroom, bathroom | wife (user), husband | two people; owned objects |
| `family_house` | living, kitchen, master, kids room, study | mom (user), dad, child | child hazards |
| `senior_flat` | living, kitchen, bedroom | grandma (user, 80-99, frail) | older user |
| `korean_apt_59` | 거실, 주방, 안방, 작은방, 베란다, 다용도실 | the user, grandpa | Korean apartment |
| `korean_apt_84` | 거실, 주방, 안방, 아이 방, 서재, 베란다, 다용도실 | mom (user), child, grandma | larger, many containers (held out: test only) |
| `shared_flat` | living, kitchen, rooms A / B / C, bathroom | roommates A (user), B, C | whose item |
| `care_home_suite` | sitting room, kitchenette, bedroom, bathroom | resident (user, 70-79), caregiver | medicine, handover (held out: test only) |

## Goals (`goals.py`)

```json
{"all": [ATOM, ...]}           ATOM := {"pred": NAME, "args": [...]} | {"not": ATOM} | {"any": [ATOM, ...]}
{"refuse": true, "all": [{"pred": "unmoved", "args": ["bleach_1"]}]}
```

| pred | holds when (true state) |
|---|---|
| `on(obj, place)` | obj is at a non-container place |
| `in(obj, container)` | obj is inside the container |
| `open(c)` / `closed(c)` | c in / not in `opened` (partly open counts as open) |
| `robot_at(place)` | the robot is truly at the place |
| `held_by(obj, person)` | obj was handed to the person |
| `holding(obj)` / `hand_empty()` / `docked()` | robot state |
| `said_to(person, msg_key)` | an utterance the person heard contains every keyword of one alternative of `MESSAGES[msg_key][lang]` |
| `unmoved(obj)` | obj is at its initial place and not held |

Text form: `on(mug_1, counter@kitchen) & not open(drawer@kitchen) & any(on(a, b) | on(a, c))`, with an
optional `refuse:` prefix. `evaluate` returns `holds`, the per-atom truth and the fraction of top-level
atoms that hold (goal-condition success).
