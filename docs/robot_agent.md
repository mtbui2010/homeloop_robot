# robot_agent robot package

`homeloop_robot/configs/` makes the mock robot a robot_agent robot package, so robot_agent's planners
(AssistLoop / ClosedLoop with the sage, grace and llm_direct planners) can run on it without ROS. It is
the only place that imports robot_agent (only `adapter.py` does, at import time).

```
PYTHONPATH=/path/to/robot_agent python -m robot_agent.contract.check_manifest --strict homeloop_robot/homeloop_robot
```

| file | content |
|---|---|
| `manifest.yaml` | robot `homeloop`: 17 skills with abstract actions (MoveTo Find Pick Place PutIn Open Close Handover Say Announce Ask Look Query Wait Dock Verify Observe), params, pre / effects, verify (symbolic + sensor `pose` / `grasp_check`), errors; capabilities; geometry (core defaults: this robot has no measured geometry); two planner notes |
| `skills_config.py` | literal `SKILL_CONFIGS`: every skill -> `homeloop_robot.configs.ra_skills.<name>` |
| `ra_skills.py` | plain `def name(node, inputs=..., **params) -> dict` functions: `get_backend().call(...)` -> `SkillResult.to_legacy()`; find adds `ins: {name: {pose_3d}}`, pose returns a tuple, ask returns `text`, grasp_check's `isdone` = holding. Results name objects as the robot perceives them ("pink cup not found", "which one? (red book, blue book)"), never by world id: an id in a message was copied by the LLM into its next step ("Find plate 1"). `move` to the charging dock also docks (robot_agent has no Dock goal; "go back and charge" is a MoveTo the dock); `wait_for_unload` = the nearest person takes the carried object (handover) |
| `backend.py` | `get_backend()` / `set_backend(robot)` / `reset_backend()`; without a backend a default robot on `senior_flat` (ideal) |
| `tasks.py` | `env_for(world)`: robot_agent ENV per place `{loc: {x, y, rz}, height, default_mode, aliases, openable}`; `ENV` of the default house. Aliases: EN / KO names and aliases, the room-qualified name (not when the name already holds the room), for the dock the words people use for charging ("charge", "충전"), and for an id with `_` its spelling with spaces (`bath cabinet@bathroom`), because robot_agent reads a key the LLM copies through its word normalizer and would otherwise ground it to the whole room |
| `adapter.py` | `Adapter` (`manifest`, `geometry`, `i18n` en / ko incl. `cannot_do`, `bind`, `observe`, `reconcile`, `pose`, `container_states`, `health`, `quiet_skills`) and `make_adapter()` |

## bind

`bind({"action": "Pick", "object": "red mug"})` -> `("pick", {"inputs": "mug_1"})`. Names are resolved on
the backend robot's world (CamelCase is split: `KitchenCounter` -> `kitchen counter`); a name that does
not resolve to exactly one thing is passed through, and the skill then fails as unknown or ambiguous.
`dock` / `charger` / `home` map to the house's dock place. Wait -> `wait` (default 5 s); Dock -> `dock`;
WaitForUnload is an alias of Handover (bound when a plan uses it, but not a plan action: robot_agent's `deliver`
goal means "take what the robot already carries, e.g. on a tray, to a place and wait until someone takes it",
which this arm robot cannot do without a Pick first; declared as its own action, it made robot_agent offer deliver
goals that compiled to MoveTo + WaitForUnload with an empty gripper, and its extra prompt lines made qwen3-vl:8b
refuse more tasks); Observe / Verify raise `Unbindable` (they are sensor skills
used by verify, not plan steps).

## People as places (delivery)

robot_agent's planners can name a person as the place to bring something to (`on(mug -> grandpa)`). `env_for`
adds an ENV entry per person (names and aliases; the speaker is also `me` / `나` / `저` in every house), and
`bind` translates `MoveTo` / `Place` of a person to `person_spot(world, pid)` (`configs/tasks.py`): the nearest
support surface (table, desk, counter, nightstand, shelf) with a free slot in the person's room whose set-down
spot is within 1.2 m of where the person is now (the outer edge of Hall's personal zone, WALTERS05 Table 1). This
uses only what every planner observes (the person's position and the furniture near them, `people_now`). It
does **not** use the judge's reach radius, height bands or posture, so the chosen surface can still be out of
reach, and the delivery then fails. With no such surface, `MoveTo` drives to the person and `Place` stays a
`place` aimed at the person, which fails ("a person, use handover"). The adapter never turns a `Place` into a
`handover`: choosing a handover is the planner's decision. robot_agent is not changed.

What this covers, measured (homeloop_bench data after review round 1): 3,269 of the 3,273 `reach` delivery
atoms go to the **speaker**, and only 4 to another person. For the speaker, sage does not name a person as the
place. With `--llm fake` (understand built from the gold goals) it asks "Where are you? Which place should I bring
it to?", the simulated user names their seat ("I'm at the sofa."), and sage then plans `on(X -> sofa)`, a seat,
which a `reach` delivery does not accept; or it flags "the me you mentioned is not in my plan" and stops at its
confirmation question. `run --planner robot_agent:sage --llm fake --split dev --limit 150 --profile ideal --lang en`:
`reach` tasks 0 / 44, `hand` 0 / 18 (34 of the 44 reach episodes asked "Where are you?"; 1 reached a `place`
call). So the person mapping only matters for deliveries to third parties (about 0.1 % of the reach atoms), and
sage's speaker deliveries go through its own "Where are you?" question and the seat it is told. The simulated
user's answer is not changed to suit sage. Test: homeloop_bench `tests/test_robot_agent_adapter.py`
(`test_sage_delivery_to_the_speaker_end_to_end`).

## How the bench drives it

`homeloop_bench`'s robot_agent adapter sets the backend to an episode-bound proxy (its `call` goes
through the episode environment: budgets, call log, interruptions), points robot_agent's `ENV` at
`env_for(world)` and runs the loop. See the bench's docs/robot_agent.md for the loop details.

## Sensed state

`observe()` and `reconcile()` use only what the robot itself reports: the believed place (a false
arrival is not visible), the believed held object (a silent slip is not visible), the containers it
opened. `container_states()` reads the container the robot stands at. `pose()` returns the noisy pose
with `age_s: 0` (no wall clock).
