# Skills

`Robot.call(skill, **args) -> SkillResult` is the one entry point (`homeloop_robot/skills.py`).
Arguments are ids or names (resolved as in [world.md](world.md)). "P" = a true-state precondition
(deterministic, `injected: false`, 1 s); "S" = a stochastic outcome of the failure model
([failure_model.md](failure_model.md), `injected: true`). Every message classifies to its code with
robot_agent's `classify_legacy_failure` (tested).

| skill | args | device | P (preconditions) | S (stochastic) | effect on success | duration |
|---|---|---|---|---|---|---|
| `move` | `target` place or person | base | unknown / ambiguous -> unreachable; already there -> ok, 0 s | hw fault; fail by target clutter, split blocked / unreachable; a blocked path stays blocked (retry / help clears it); timeout; false arrival (ok, pose 0.6 m off, at no place); drop of the held object in transit (ok, object on the floor); protective stop longer than the stop timeout -> blocked | at = target, pose = approach pose, found objects forgotten, undocked; to a person: 1.2 m before the person along the path | path length / `move.speed_mps`, stretched by the safety monitor |
| `find` | `obj` | camera | unknown name -> absent; a name several objects fit ("mug") -> looked for here: none in view -> absent, one -> that one, several -> one of them (drawn; `data.candidates` lists the ones seen here; gate pilot round 1); camera down -> perception_unavailable; not visible here (elsewhere, closed or partly open container) -> absent; not at a place (e.g. beside a person with no surface) -> absent (it looks where it stands and does not see it) | hw fault; camera dropout (clears with wait); miss -> absent; wrong instance (ok, `data.found` = a confusable object here); false positive (ok, the object is not here) | `data.found` added to the found set | `find.duration_s` |
| `pick` | `obj` | arm | holding -> grasp_failed; a name several objects fit -> the one found here (one perceived object at this place), else absent; not truly visible here -> absent (an object visible here but not found yet is detected first, with the find miss rate); phantom -> absent; heavy / fixed -> grasp_failed ("too heavy"); in a partly open container -> unreachable; high shelf > 1.5 m -> unreachable | hw fault; fail by clutter (or grasp class), split absent / unreachable / blocked / grasp_failed; a hard instance (retry success `pick.p_retry_success`); silent slip (ok, hand empty) | holding = obj | half of `pick_place.duration_s` |
| `place` | `target` place | arm | not holding -> absent ("no object held"); target a person -> unreachable; not at target -> unreachable; closed or partly open container -> blocked; full -> blocked | hw fault; drop -> dropped (floor); silent fall (ok, object on the floor) | obj on / in target | half of `pick_place.duration_s` |
| `put_in` | `container` | arm | target not a container -> unreachable; otherwise as `place` | as `place` | obj inside | as `place` |
| `open` | `container` | arm | not at it -> unreachable; not openable / not a container -> blocked; holding -> blocked; already open -> ok, 0 s | hw fault; fail by door / drawer, split blocked / unreachable (the handle); stuck (retry success p); silent partial open | opened | `open.duration_s` |
| `close` | `container` | arm | as `open`; already closed -> ok, 0 s | as `open` (no partial) | closed | `close.duration_s` |
| `handover` | `person` ("" = nearest within 3 m) | arm | not holding -> grasp_failed; nobody within 3 m in this room -> unreachable | hw fault; the person does not take it -> timeout; drop -> dropped | obj at `person:<id>` | `handover.duration_s` + the person's take latency |
| `say` | `text`, `lang` | speaker | empty text -> software | hw fault | utterance logged with the people who heard it | words / `say.words_per_s` |
| `announce` | `text`, `lang` | speaker | as `say` | as `say` | heard in this room and adjacent rooms | as `say` |
| `ask` | `question`, `lang` | speaker | nobody in hearing range -> timeout | no answer -> timeout; the answer passes through ASR noise (user model) | `data.answer`; an answered ask while a path is blocked counts as a help request | speech + answer latency (or + `ask.timeout_s`) |
| `look` | - | camera | camera down -> perception_unavailable | per visible object a miss; a false positive adds a confusable class | `data.visible`, `data.containers` (this room), `data.people` (this room) | `look.duration_s` |
| `vlm_check` | `query` (a goal atom, names allowed) | camera | camera down -> perception_unavailable; unparsable -> ok, `answer: unknown` | false yes `vlm.p_false_yes`, false no `vlm.p_false_no` | `data.answer` yes / no | `vlm.duration_s` |
| `wait` | `seconds` (0 < s <= 120) | - | bad value -> software | a camera fault clears (s >= 5) | - | s |
| `dock` | - | base | not at the dock -> unreachable | hw fault | docked | `dock.duration_s` |
| `grasp_check` | - | gripper | - | wrong reading `grasp_check.p_wrong` | `data.holding` (sensed) | `grasp_check.duration_s` |
| `pose` | - | base | - | noise `pose.sigma_m` | `data.pose` [x, y, yaw]; `data.at` within 0.3 m of an approach pose | `pose.duration_s` |

Motion skills (e-stop, interruptions, safety, random e-stops): move, pick, place, put_in, open, close,
handover, dock.

## Result

`SkillResult(ok, code, msg, data, duration_s, injected, truth)`. `public()` = ok, code, msg, data,
duration (what a planner sees); `to_legacy()` = robot_agent's `{isdone, msg, code?}` + data;
`to_json()` adds `injected` and `truth` (traces only: `effect`, `event` such as `slip`, `fall`,
`false_arrival`, `wrong_instance`, `drop_in_transit`).

## Robot API besides `call`

- `observe()`: sensed state: `pose_est` (noisy), `at` as the robot believes it, `holding_sensor`,
  `estop`, `health` (per device ok / fault).
- `believed`: the robot's belief from its own reports (at, holding, opened).
- `schedule_interrupt(after_motion_calls, UserEvent)`: the runner arms a scripted interruption; motion
  call number `after_motion_calls + 1` returns `cancelled` and the event is delivered.
- `pop_events()`: user events delivered since the last call (scripted, or from the user model's
  `events_between`).
- `trace`: one record per call (call, args, start time, duration, `to_json()`).

Safety integration: `move` calls `safety.traverse("move", path, speed, t0, user.people_at, part="base",
collaborative_with=<person target>)`; arm skills call it with `part="arm"` and `path=[robot_xy]` and add
the returned `duration_s` as extra time; `aborted` fails the skill `blocked`. Pick, place, put_in and
handover call `hazards.check_call` before their effect; events go to `world.semantic_violations` (the
robot still executes: refusing is the planner's job).
