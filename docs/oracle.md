# Oracle

`homeloop_robot.oracle` plans over the TRUE world (privileged): exact object locations, open and partly
open containers, what the robot holds, active faults.

```python
solve(world, goal, *, avoid_hazards=True, max_calls=60, lang="en", people_pos=None) -> list[Call] | None
explain_unsolvable(world, goal) -> str          # "" when solvable
rollout(episode, goal, *, max_calls=60, max_time_s=1800, max_attempts=3) -> {"success", "calls", "status"}
```

`solve` returns the calls that reach the goal from the current state in the `ideal` profile, or None:
an invalid goal, a heavy / fixed object, an object out of reach (high shelf above 1.5 m), a container
that does not open, a person not in the house, a goal that needs a semantic hazard (when the hazards
module is installed and `avoid_hazards`), an object already moved for an `unmoved` atom, or more than
`max_calls` calls. `people_pos` overrides people's start positions (e.g. from `user.people_at(t)`).

Plan construction (deterministic, ties by id):

- already-true atoms are skipped; `any(...)` takes the cheapest alternative (path length, then calls);
- object atoms first, nearest-first greedy from the robot's start pose (a fixed point, so re-solving
  after every call gives the same order), then `said_to`, then `open` / `closed`, then `robot_at` /
  `docked` / `hand_empty`, then `holding` last;
- `on(o, p)`: (open o's container if closed) move, find, pick, move p, place;
- `in(o, c)`: open c first (it needs an empty hand), then fetch o, move c, put_in; a partly open
  container is closed and opened again;
- `delivered(o, person)`: the mode comes from `delivery_modes` / `reach.choose_mode` (the request's words,
  the house profile, the furniture around the person), never from the atom's `mode` label (`_own_modes` replaces
  it before planning). reach: fetch, move to the nearest reachable support surface with room, place; with none
  left (the person moved), or mode hand: fetch, move to the person, handover. Pass `text=` (the request) or
  `modes=` (from `delivery_modes` at the episode start) to `solve`; `rollout(..., text=)` fixes the modes once;
- `held_by(o, person)`: fetch, move to the person, handover; `said_to(person, key)`: move to the person,
  say the key's canonical sentence (`catalog.MESSAGE_TEXT`) in `lang`;
- a held object no goal needs is put back where it started, or on the nearest free surface.

`rollout` is the closed-loop reference behaviour used by the tests: re-solve from the truth after every
call, at most 3 consecutive failures of the same call, a 5 s wait before retrying `perception_unavailable`
or `blocked`, an `ask` for help after a blocked move, give up on a persistent fault or e-stop. The bench's
`oracle` planner implements the same policy through its own environment.

Tests (`tests/test_oracle.py`): every house, 50 random reachable goals each, executing the plan through
the robot in `ideal` reaches the goal; unsolvable goals return None; `any` takes the cheaper branch; the
closed-loop composition target of [failure_model.md](failure_model.md).
