# Failure model

How a skill call's stochastic outcome is drawn (`homeloop_robot/outcomes.py`, `skills.py`). The numbers
are profile parameters ([profiles.md](profiles.md)); their sources are in [calibration.md](calibration.md).

## Order of a call

1. Arguments are checked against `SKILL_SPECS`: a bad call fails `software` and takes no time.
2. Global states: an e-stop makes every motion skill fail `estop`; a persistent hardware fault on the
   skill's device makes it fail `hw_fault`.
3. A pending user interruption cancels the motion call (`cancelled`), effects not applied.
4. True-state preconditions (deterministic, `injected: false`): the object is not here, the hand is full,
   the container is closed, the object is too heavy, the target is unknown or ambiguous ... A failed
   precondition takes 1 s of simulated time.
5. The failure model (`injected: true`), rules in this order:
   1. hardware fault: `hw.p_per_motion_call` (base, arm) or `hw.p_per_sensor_call` (camera, speaker,
      gripper, pose); with `hw.p_persistent` the device stays faulted for the episode;
   2. skill failure from the skill's table: `move.p_fail[clutter of the target]`,
      `pick.p_fail[clutter of the place]` (or `pick.p_fail_class[grasp class]` for deformable objects),
      `open.p_fail` / `close.p_fail[door | drawer]`;
   3. the failure code from the skill's `split` (`grasp_failed` only for pick; an articulated-object
      handle failure is `unreachable`);
   4. silent failure (the call reports ok, the effect is not applied): `verify.p_false_success` for
      pick (slip: hand empty), place / put_in (the object falls to the floor) and open (only partly
      open: objects inside cannot be reached or added);
   5. perception: find miss `find.p_miss`, false positive `find.p_false_positive` (find reports an
      object that is not there), wrong instance `find.p_wrong_instance[few | many]` (find reports a
      confusable object at the place);
   6. transport: after a successful move while holding, `carry.p_drop` puts the object on the floor of
      the destination room (the move still reports ok); `place.p_drop` / `handover.p_drop` fail the call
      `dropped`.
6. Effects on the true world.
7. Duration from the profile, stretched by the safety monitor (slow zones, protective stops).

Random e-stops: before each motion call, with probability `1 - exp(-estop.rate_per_h * t / 3600)` for
the call's nominal time `t`. The robot cannot reset an e-stop itself.

## Common random numbers

Every call draws a fixed vector of 14 uniforms from
`rng_for(seed, episode_key, "outcome", skill, canonical_args, nth)`, where `nth` counts earlier calls
with the same skill and arguments. Each rule reads its own slot. Two planners that make the same call
in the same episode get the same outcome for it, whatever else they did, so paired comparisons
(McNemar on (task, seed)) have less variance.

## Faults that outlive a call

| fault | device key | how it clears |
|---|---|---|
| persistent hardware fault | `base`, `arm`, `camera`, `speaker`, `gripper` | never (the episode is lost for that device) |
| camera / detector down | `camera` | a `wait` of at least 5 s clears it with `perception.p_clear_on_wait` |
| blocked path | `path:<target>` | each retry of the same move clears it with `move.p_retry_clears_blocked` (STRANDS); an `ask` that a person answers clears it with `move.p_help_clears_blocked`; carpet places use `move.p_stuck_retry_success` |
| hard grasp instance | `grasp:<object>` | the next pick succeeds with `pick.p_retry_success` (Contact-GraspNet retry) |
| stuck container | `container:<id>` (`:close`) | the next open / close succeeds with `open.p_retry_success` / `close.p_retry_success` |

A move that reports success can still be a false arrival (`move.p_false_arrival_hard` for `hard_nav`
targets, `move.p_false_arrival_normal` otherwise): the true pose is 0.6 m off and the robot is at no
place; `pose` shows it (no `at`), and find there reports `absent`.

## Composition target (checked loosely, not tuned)

`tests/test_oracle.py::test_closed_loop_oracle_composition` runs the closed-loop oracle
(`oracle.rollout`) on single-object rearrangement in every house. In `ideal` it succeeds every time; in
`real` it should land in the band spanned by published end-to-end numbers, which we do not tune toward:

- OK-Robot pick-and-drop 58.5 % (cluttered) to 82 % (cleaner homes), https://arxiv.org/abs/2401.12202;
- SayCan execution 60 % (real kitchen) to 74 % (mock kitchen), Table 2, https://arxiv.org/abs/2204.01691;
- lower reference points: HomeRobot OVMM real end-to-end 15-20 %, Table 4, https://arxiv.org/abs/2306.11565,
  and DynaMem long-horizon home tasks 9 / 17, https://arxiv.org/abs/2411.04999.

Measured on this repository with the Null user and safety monitor (oracle rollout, 8 houses, 40 random
goals each, 1-3 atoms; 2026-11-02): ideal 1.00,
real 0.75 (single `on` goals 0.87), stress 0.51 (single `on` 0.55). The test's band for `real` single-object
goals is 0.5-0.95; a value outside it is reported, not tuned away.
