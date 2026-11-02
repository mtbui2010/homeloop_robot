# homeloop_robot: rules for agents

A stochastic mock household robot: full skill set, no motion; skills check the TRUE symbolic world
and return success or a typed failure drawn from failure rates calibrated from published papers.

## Rules
- Python: `~/miniconda3/envs/vlaserve/bin/python` (3.12); run with `PYTHONDONTWRITEBYTECODE=1`.
- Tests: `python -m pytest -q tests` (green, < 120 s, no network). Do not commit while tests fail.
- Runtime deps: stdlib + pyyaml only. No ROS, GPU, network.
- robot_agent is imported ONLY under `homeloop_robot/configs/` (the optional robot package).
- No private project / company names anywhere (see docs/testing.md for the grep).
- Determinism: all randomness through `homeloop_robot.rng`; no wall clock, `hash()`, set order in output;
  JSON with `sort_keys=True` and floats rounded by `rng.r6`.
- Never fabricate numbers or sources: a calibrated value needs a source listed in docs/calibration.md
  with the page / table; otherwise mark it `assumed: true` with a note.
- `python -m homeloop_robot.profiles validate --strict` and `... profiles consistency --strict` must pass after
  any profile or skill change; `python -m homeloop_robot.realism --strict` after any catalog / house change.
- GPU: never needed here (the bench's LLM tool uses GPU 0 only).
- Commits: explicit `git add <paths>`; message ends with the attribution lines; no push.

## Docs
- [Architecture](docs/architecture.md): modules, call flow, determinism
- [World and houses](docs/world.md): entities, house YAML schema, goal language
- [Skills](docs/skills.md): every skill, preconditions, outcomes, durations
- [Failure model](docs/failure_model.md): how outcomes are drawn, faults, recovery
- [Profiles](docs/profiles.md): ideal / real / stress, YAML schema, validator
- [Calibration](docs/calibration.md): every source and what was taken from it
- [Oracle](docs/oracle.md): the privileged planner over the true world
- [robot_agent package](docs/robot_agent.md): manifest, adapter, how the bench drives it
- [Realism](docs/realism.md): object provenance, placement / house rules, outcome consistency
- [Safety](docs/safety.md): standards, separation formulas, the safety monitor
- [Simulated user](docs/user_model.md): dialog, ASR noise, interruptions, motion, sources
- [Hazards](docs/hazards.md): semantic hazard codes and checks
- [Testing](docs/testing.md): test map, selftest, checks
