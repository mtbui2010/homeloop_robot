# Testing

```
cd homeloop_robot
PYTHONDONTWRITEBYTECODE=1 ~/miniconda3/envs/vlaserve/bin/python -m pytest -q tests        # < 120 s, no network
PYTHONPATH=/path/to/robot_agent ... -m pytest -q tests                                    # + robot_agent tests
```

| test | what |
|---|---|
| `test_types.py` | result shapes; FailureCode values equal robot_agent's (skipped without robot_agent) |
| `test_rng.py` | seeds, streams, `r6` |
| `test_houses.py` | at least 8 houses; `validate_house` on every house (incl. the ideal-safety clearances) |
| `test_world.py` | seed 0 = YAML default, layouts vary with the seed, resolvers EN / KO, paths, deep copy |
| `test_goals.py` | parse / format round trip, validate, evaluate incl. `said_to` |
| `test_skills.py` | every skill's preconditions and effects in `ideal`; injected failures with patched profiles (hardware faults, blocked paths, silent failures, drops, camera faults, false arrivals, interruptions); every failure message classifies to its code with robot_agent's classifier |
| `test_outcomes.py` | failure tables, branches, split shares and failure rates match the profile empirically |
| `test_profiles.py` | key sets, ideal zeros, stress scaling, `validate --strict` passes |
| `test_determinism.py` | same seed -> same trace, common random numbers, oracle determinism |
| `test_oracle.py` | 50 random goals per house solved in `ideal`; unsolvable goals; closed-loop composition band |
| `test_selftest.py` | selftest byte-identical, ideal differs from real |
| `test_realism.py` | catalog completeness, every house passes R-a..R-h, placement rules |
| `test_consistency.py` | binomial test; every rate check at n = 1500; physical possibility on short traces |
| `test_configs_adapter.py` | ENV shape, legacy skill dicts; with robot_agent: `check_manifest --strict`, adapter bind / observe |

Tests build episodes with `user_impl="null", safety_impl="null"` (tests/helpers.py) so they do not depend
on the user / safety models; `test_determinism.py` also runs with the full models when installed.

## Command-line checks

```
python -m homeloop_robot.selftest --seed 7 --episodes 30 --profile real --out /tmp/a.jsonl   # deterministic trace
python -m homeloop_robot.profiles validate --strict
python -m robot_agent.contract.check_manifest --strict homeloop_robot/homeloop_robot          # robot_agent on PYTHONPATH
grep -rniE '<private names>' . --include=*.py --include=*.yaml --include=*.md               # no private names
```

The selftest writes, per episode, 25 calls (each with p 0.6 the next oracle call toward a random
reachable goal, else a random skill with random valid arguments) and a summary line; two runs with the
same arguments give byte-identical files and the `ideal` and `real` traces differ.
