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
| `adapter.py` | `Adapter` (`manifest`, `geometry`, `i18n` en / ko incl. `cannot_do` and the Korean narration milestones and verbs of robot_agent's Announcer (its core table has no Korean), `bind`, `observe`, `reconcile`, `pose`, `container_states`, `health`, `quiet_skills`) and `make_adapter()` |

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

Where this is applied (R2-5 B1). robot_agent's AssistLoop (`assist_loop._bind`) overwrites the adapter's bind
result with the raw ENV key for `MoveTo` / `Place`, so the skill functions receive the person's ENV key. The ENV
entry of a person therefore records `person` (the id) and `spot` (the `person_spot` of the start world, or
None), and `ra_skills.move` / `ra_skills.place` of a person key go to that spot (or to the person). The entry's
`loc` is the spot, or, with no spot, the point where a move to the person stops: `skills.person_stop_xy`, the
point `move.person_standoff_m` (1.2 m) before the person on the path from the charging dock (the way into their
room). The robot's own `move(person)` stops at that same point from wherever it starts, so the base ends within
robot_agent's `arrive_tol` (0.3 m) of the ENV loc and its arrival check holds. If the person walks away
meanwhile, the entry is stale like any ENV place and the check can fail, as it would on a real robot with a
fixed map. Tests: homeloop_bench `tests/test_reach_ra_bind.py` (the real AssistLoop bind path, every house and
person) and `tests/test_person_move.py`.

Person keys (R2-5 B2, pilot round 1). AssistLoop reads a goal place that normalises to `me`, `user`, `here`,
`you`, `myself` or `person` as "the user, place unknown" and asks where they are, so no ENV key may be such a word.
AssistLoop also reads a plan back with the ENV key itself ("I will put the mug on the {key}.", `AssistLoop.summary`),
so a person's key is what the user hears and is never a raw id (`person_user`, `partner_b` reached the user in
pilot round 1). `tasks.person_keys`: the speaker's entry is `spot within your reach` (the read-back is said to them; its
aliases keep their name and me / 나 / 저), anyone else's is their English name without the article (`husband`,
`grandpa`, `kid`, `roommate b`); a name that is a reserved word, a place key or another key falls back to the id.
`ra_skills` and `Adapter.bind` map a key back to the person id (`Handover spot within your reach` -> `handover
user`). The key must not end in a word of everyday requests: robot_agent also takes the last word of a multi-word
ENV head as a place phrase (`understand._phrases`), so the earlier key `spot near you` made every "you" ("Can you
put ...", 3,947 of 6,000 dev / test EN instructions) a mention of the speaker's spot: "You mentioned the you. What
should I do there?" (fresh pilot round 1, hl-dev-000057 / 000016; `tests/test_dialog_fresh_pilot_r1.py`, homeloop_bench
`tests/test_person_key_mentions.py`).
Tests: `tests/test_person_keys.py`, homeloop_bench `tests/test_reach_ra_bind.py` and `tests/test_pilot_r1.py`.

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

## Say language

robot_agent passes `lang` only to Ask. `say` / `announce` (configs/ra_skills.py) therefore take the language from
the sentence itself (`speech_lang`): Hangul -> ko, Latin letters -> en, neither -> the given `lang` or the
episode's language. A Korean message is said in Korean and reaches a Korean listener; an English sentence in a
Korean episode stays English (R2-6 H1, tests/test_say_lang.py; the bench runs a KO message task through the real
AssistLoop in tests/test_say_lang_ra.py).

## Seed pool

`planner/seed_memory.jsonl` (manifest `planner.seed_memory`) is the pool of solved examples SAGE retrieves from
(top 3 by similarity into its prompts). 12 examples, 7 EN and 5 KO, in robot_agent's memory format, written for
`example_flat` (the bench's progprompt example house, used by no split): delivery to a surface beside the person
(`Place` on the person) and by handover, open before pick, putting into a closed container, messages, refusals,
a two-object task. Every example is hand-written for example_flat (its `origin` says so) and has a goal that no
dev / test task has: its objects and messages were chosen for that (the two messages, `take_umbrella` and
`bath_ready`, are `catalog.EXAMPLE_MESSAGES`, used by no task; pilot round 2 replaced seeds whose goals were
dev / test goals, e.g. said_to(son, leaving_soon)). Extra fields (`lang`, `shows`, `house`, `goal`, `origin`) are ignored by robot_agent and used by
the tests: tests/test_seed_pool.py (format, coverage, embodiplan's action model with this robot's plan actions) and
the bench's tests/test_seed_pool_leak.py (no dev / test leak; each plan reaches its goal on the mock robot). The
bench's `robot_agent:sage_norag` runs the same SAGE without the pool. robot_agent also hands the pool to its other
planners (grace, llm_direct's examples), as it does for any robot that ships one.

## How the bench drives it

`homeloop_bench`'s robot_agent adapter sets the backend to an episode-bound proxy (its `call` goes
through the episode environment: budgets, call log, interruptions), points robot_agent's `ENV` at
`env_for(world)` and runs the loop. See the bench's docs/robot_agent.md for the loop details.

## Sensed state

`observe()` and `reconcile()` use only what the robot itself reports: the believed place (a false
arrival is not visible), the believed held object (a silent slip is not visible), the containers it
opened. `container_states()` reads the container the robot stands at. `pose()` returns the noisy pose
with `age_s: 0` (no wall clock).
