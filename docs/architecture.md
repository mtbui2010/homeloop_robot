# Architecture

`homeloop_robot` is a mock household robot. It has a full skill set but no motion: each skill checks
the TRUE symbolic world, then returns success or a typed failure drawn from failure rates calibrated
from published papers ([calibration.md](calibration.md)), with a simulated duration.

## Modules

| module | role |
|---|---|
| `types.py` | `FailureCode` (same values as robot_agent's), `SkillResult`, `Call`, `FaultState`, user / safety protocols and dataclasses |
| `rng.py` | `derive_seed`, `rng_for`, `Streams`, `r6`: every random draw |
| `clock.py` | `SimClock`: simulated time, advanced by skill durations |
| `catalog.py` | 56 object classes (EN / KO names, grasp class, tags, confusable classes; provenance, mass, size, typical receptacles), receptacle categories, colours, message keys |
| `world.py` | `World` (true state), houses, resolvers (EN / KO names, colours, owners), geometry (paths through doors) |
| `houses/` | 8 house layouts (YAML) + `validate_house` ([world.md](world.md)) |
| `goals.py` | goal-condition language: parse / format / validate / evaluate |
| `profiles/` | `ideal` / `real` / `stress` parameter sets + validator ([profiles.md](profiles.md)) |
| `outcomes.py` | the failure model's tables and draws ([failure_model.md](failure_model.md)) |
| `skills.py` | `Robot.call(skill, **args)`, `SKILL_SPECS` ([skills.md](skills.md)) |
| `episode.py` | `make_episode`: world + robot + user model + safety monitor; `NullUser`, `NullSafety` |
| `oracle.py` | `solve` over the true world, `rollout` (closed-loop reference) ([oracle.md](oracle.md)) |
| `realism.py` | catalog / house realism rules R-a, R-b, R-c, R-d, R-h ([realism.md](realism.md)) |
| `consistency.py` | outcome-rate and physical-possibility checks (`profiles consistency`) |
| `selftest.py` | `python -m homeloop_robot.selftest`: a deterministic JSONL trace ([testing.md](testing.md)) |
| `configs/` | the robot_agent robot package (manifest, skills, adapter) ([robot_agent.md](robot_agent.md)) |
| `user.py`, `asr.py`, `dialog.py`, `safety.py`, `hazards.py` | the simulated user, ASR noise, dialog policy, safety monitor and semantic hazards (robot-human-safety part; optional at import time) |

## Call flow

```
planner -> Robot.call("pick", obj="mug_1")
             1 args vs SKILL_SPECS            -> software (no time)
             2 e-stop / persistent hw fault   -> estop / hw_fault
             3 user interruption              -> cancelled
             4 true-state preconditions       -> e.g. absent, grasp_failed ("too heavy")   injected=False
             5 failure model (profile)        -> e.g. grasp_failed, silent slip            injected=True
             6 effects on World
             7 duration (profile; safety monitor stretches motion) -> SimClock
           <- SkillResult(ok, code, msg, data, duration_s, injected, truth)
```

`SkillResult.public()` is what a planner may see; `truth` (the real effect, silent failures, false
arrivals) is for traces and metrics only. `make_episode` uses the simulated user and the safety monitor
when they are installed, else `NullUser` (hears instructions, never answers, takes handovers, never
moves) and `NullSafety` (no slow-down; separation measured from geometry).

## Determinism

No wall clock, no `random` module functions, no `hash()`, no set order in any output. Draws are keyed
by name (`rng_for(seed, episode_key, "outcome", skill, args, nth)`), so two runs with the same arguments
give byte-identical traces and two planners get the same outcome for the same call (common random
numbers). JSON output uses `sort_keys=True` and floats rounded by `r6`.

## Dependencies

Python >= 3.10, stdlib and pyyaml. robot_agent is imported only under `homeloop_robot/configs/`.
