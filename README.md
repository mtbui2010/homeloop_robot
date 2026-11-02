# homeloop_robot

A stochastic mock household robot for benchmarking task planners. It has a full household skill set
(move, find, pick, place, put in, open, close, hand over, say, announce, ask, look, VLM check, wait, dock,
grasp check, pose) but does no motion: each skill checks the TRUE symbolic world state and returns
success or a typed failure (`absent`, `unreachable`, `blocked`, `grasp_failed`, `dropped`, `hw_fault`,
`perception_unavailable`, `timeout`, `estop`, `cancelled`, `software`), drawn from failure rates
calibrated from published papers, with simulated durations. Silent failures (a slip that reports
success), false arrivals, wrong instances, blocked paths that need help, and persistent hardware faults
are modelled. It is seeded and fully deterministic, pure Python (stdlib + pyyaml), with no ROS, GPU or
network.

It is the robot under HomeLoop-Bench (`homeloop_bench`), and it ships an optional robot_agent robot
package (`homeloop_robot/configs/`).

## Install

```
pip install --no-deps --no-build-isolation -e .
```

## Quick start

```python
from homeloop_robot import make_episode, goals, oracle

ep = make_episode("senior_flat", seed_state=0, profile="real", seed=1, key="demo")
r = ep.robot.call("move", target="kitchen counter")
r = ep.robot.call("find", obj="red mug")          # SkillResult(ok, code, msg, data, duration_s, ...)
goal = goals.parse("on(mug_1, coffee_table@living)")
print(oracle.solve(ep.world, goal))               # the oracle's calls from the true state
print(goals.evaluate(goal, ep.world))
```

```
python -m homeloop_robot.selftest --seed 7 --episodes 30 --profile real --out trace.jsonl
python -m homeloop_robot.profiles validate --strict
python -m homeloop_robot.profiles consistency --strict   # simulated rates vs the cited rates (~3 min)
python -m homeloop_robot.realism --strict                # catalog provenance, placements, house plausibility
python -m homeloop_robot.profiles show stress
```

## Profiles

`ideal` (no failures, no noise), `real` (calibrated; every parameter has a source or is a documented
assumption), `stress` (failure probabilities doubled, sourced worst cases). See
[docs/profiles.md](docs/profiles.md) and [docs/calibration.md](docs/calibration.md).

## Docs

[architecture](docs/architecture.md) · [world and houses](docs/world.md) · [skills](docs/skills.md) ·
[failure model](docs/failure_model.md) · [profiles](docs/profiles.md) · [calibration](docs/calibration.md) ·
[oracle](docs/oracle.md) · [robot_agent package](docs/robot_agent.md) · [realism](docs/realism.md) ·
[testing](docs/testing.md)

## License

Apache-2.0 ([LICENSE](LICENSE)).
