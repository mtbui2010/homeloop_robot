# Profiles

A profile is a directory under `homeloop_robot/profiles/`. Load one with
`homeloop_robot.load_profile("real")`; `Profile.get(name)`, `Profile.entry(name)`, `Profile.sha`
(SHA-256 of the resolved values).

| profile | what |
|---|---|
| `real` | the calibrated values, in fragments `real/skills.yaml` (robot skills), `real/user.yaml`, `real/safety.yaml` (user model and safety; robot-human-safety part) |
| `ideal` | derived from `real`: every `role: failure / user_noise / safety_noise` probability and rate is 0 (so ASR noise, wrong / unsure answers and moving people are off), `pose.sigma_m` 0; durations and safety formulas unchanged |
| `stress` | derived from `real`: every `role: failure` probability `p -> min(0.95, 2p)` and failure rate `r -> 2r`; recovery probabilities unchanged (scaling them would make stress easier); sourced worst cases replace scaled values (`open.p_fail` = 0.5, articulated-object BC policy, arXiv 2401.14403) |

## Parameter entry (`real/*.yaml`, under `params:`)

```yaml
move.p_fail:
  kind: prob_map                 # prob prob_map split range_s range duration_s speed_mps accel_mps2 distance_m
                                 # mass_kg rate_per_h count lognormal normal categorical flag words_per_s value map
  role: failure                  # failure | recovery | nominal | user_noise | safety_noise
  keys: [low, medium, high]
  value: {low: 0.0067, medium: 0.02, high: 0.025}
  source: https://arxiv.org/abs/2401.12202
  where: "Sec. III-C, Fig. 6; Fig. 4"
  note: "OK-Robot navigation error by clutter level ..."
perception.p_unavailable:
  kind: prob
  role: failure
  value: 0.01
  assumed: true
  anchor: https://arxiv.org/abs/2212.00922      # optional: nearest source and why it was not used directly
  note: "No per-call camera dropout rate was found ..."
```

`PARAM_REGISTRY` in `profiles/__init__.py` lists every parameter the code reads (robot skills, and
between the `user-safety` markers the user / ASR / safety parameters). A parameter the code reads with a
default (`Profile.get(name, default)`) is one owned by the other part, used only when that part is
installed.

## Validator

`python -m homeloop_robot.profiles validate [--strict]` (also `show NAME`, `list`). Rules, each printed
PASS / FAIL; exit 0 only if all pass; `--strict` also fails on warnings:

1. `real` loads, fragments have no duplicate keys, key set == `PARAM_REGISTRY`;
2. every entry has kind, role, value, note (>= 20 characters); values type-check (probabilities in
   [0, 1], splits sum to 1 and use FailureCode keys, ranges lo <= hi, durations > 0, declared map keys);
3. sourced entries: `source` is a URL / `doi:10.x` / `arXiv:NNNN.NNNNN`, `where` is given, and the source
   is listed in [calibration.md](calibration.md) (arXiv ids normalised from abs / pdf / arXiv: forms,
   DOIs lower-cased);
4. `assumed: true` entries have a note; an `anchor` obeys rule 3; they are counted and listed;
5. `ideal`: every failure / noise probability and rate is 0, `user.motion.rate_per_h` 0, keys == real,
   values == an independent re-derivation;
6. `stress`: derived from `real`, the scaling has a note and a source or `assumed: true`, every override
   has a value, a note and a listed source or `assumed: true`, values == an independent re-derivation,
   all probabilities <= 1;
7. calibration.md exists; a source it lists that no parameter, profile file or other doc uses is a
   warning.

The output ends with `assumed: N params` and their names. A derivation rule for a parameter family that
is not installed (e.g. `user.*` before the user model is merged) is printed as INFO, not a warning.

## Overrides for sensitivity runs

`load_profile("real+asr.ko.app_cer=0.02,asr.en.app_wer=0.02")` returns `real` with those scalar parameters set
(each marked `override: true`; unknown keys, non-numbers and probabilities outside [0, 1] are refused). The
profile's `sha` changes, so a run records which values it used. The bench passes it with
`homeloop-bench run ... --set KEY=V[,KEY=V]`; `python -m homeloop_robot.report asr-share --profile` takes the
same form. Overridden profiles are for sensitivity analysis only; `validate --strict` checks the three named
profiles.
