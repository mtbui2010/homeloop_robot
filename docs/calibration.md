# Calibration sources

Every stochastic parameter of the `real` profile comes from a published source listed here, or is an
assumption listed in [Assumptions](#assumptions). `python -m homeloop_robot.profiles validate --strict`
checks that every `source:` and `anchor:` of a parameter appears in this file, and warns when this file
lists a source that nothing uses.

How the numbers were collected: each source below was opened (arXiv HTML / abstract pages, or the PDF
converted to text) during the research for this repository, and the number was read at the location
given. A "derived" value is arithmetic on the published numbers, shown in the parameter's `note:` in
`homeloop_robot/profiles/real/*.yaml`. Nothing here is a value we measured ourselves.

How to read the mapping: most papers report task-level success. We take per-attempt numbers where a
paper gives them (Contact-GraspNet first try vs. retry, BINDER's stage-wise funnel, STRANDS recovery
attempts) and say so when a task-level number stands in for a per-call one.

## Robot skills (robot-core)

### OKR: OK-Robot
Liu et al., "OK-Robot: What Really Matters in Integrating Open-Knowledge Models for Robotics", 2024.
https://arxiv.org/abs/2401.12202

- Sec. III-C, Fig. 6: navigation error 15 / 12 / 4 % and manipulation error 25 / 16 / 13 % of trials for
  no / low / high cleanup. -> `move.p_fail`, `pick.p_fail` (our clutter high / medium / low).
- Sec. III-D: of 171 trials in 10 homes, semantic-memory retrieval failure 9.3 % (-> `find.p_miss`) and
  robot hardware failure 7.5 % (-> `hw.p_per_motion_call` = 0.075 / 4 motion primitives per trial).
- Sec. V-E: 1 kg payload limit of the robot. -> `carry.payload_kg`, `catalog.PAYLOAD_KG`.
- Abstract, Fig. 1, Sec. III-A: 58.5 % pick-and-drop success in cluttered homes, 82 % in cleaner ones
  (composition target, docs/failure_model.md).

### STR: STRANDS
Hawes et al., "The STRANDS Project: Long-Term Autonomy in Everyday Environments", 2016.
https://arxiv.org/abs/1604.04384

- Table 2: recovery attempts by failure type. Navigation failure (no valid path) 707 of 1,700 successful
  (-> `move.p_retry_clears_blocked` = 0.416); bumper pressed with a help request 177 of 325 (->
  `move.p_help_clears_blocked` = 0.545); stuck on carpet 16 of 263 (-> `move.p_stuck_retry_success` = 0.061).
  "Successful" means no further failure within 1 min or 1 m (Sec. 7).
- Sec. 6 and Table 1: in 2015, 7 runs over 1,499 h of cumulative runtime; one ended by a user intervention
  (a person powered the robot off). -> `estop.rate_per_h` = 1 / 1499 (a proxy for a person stopping the robot).

### COB: CoBots
Biswas and Veloso, "Localization and Navigation of the CoBots Over Long-term Deployments", IJRR 2013.
https://www.ri.cmu.edu/pub_files/2013/12/ijrr_longterm_autonomy_cobot.pdf

- Sec. 4 (Results), Fig. 12: localization errors in the worst region, 10 in 263 visits (0.038).
  -> `move.p_false_arrival_hard`; anchor for the assumed `move.p_false_arrival_normal`.
- Sec. 5 (Failures): the robot asks for help after 5 minutes without progress. -> `move.timeout_s` = 300.

### BIND: BINDER
Cho et al., "BINDER: Instantly Adaptive Mobile Manipulation with Open-Vocabulary Commands", 2025.
https://arxiv.org/abs/2511.22364

Office trials (3 tasks x 40), not homes.
- Sec. IV-D, Fig. 7: navigation reached the target in 114 / 120; of the 6 failures 4 were collision-risk stops
  and 2 localization / target errors. -> `move.split` (blocked 4/6, unreachable 2/6).
- Fig. 7: 12 grasp-stage failures of 114: 3 not detected, 2 no valid pose, 3 collisions, 2 failed grasps,
  2 drops after pickup. -> `pick.split` (the 10 non-drop failures), `carry.p_drop` = 2 / 114.
- Fig. 7: 2 drops while placing of 102. -> `place.p_drop`; anchor for the assumed `handover.p_drop`.

### CGN: Contact-GraspNet
Sundermeyer et al., "Contact-GraspNet: Efficient 6-DoF Grasp Generation in Cluttered Scenes", ICRA 2021.
https://arxiv.org/abs/2103.14127

- Table I, Sec. IV-C: 84.31 % success on the first attempt, 90.20 % within two attempts (51 unseen objects,
  9 cluttered scenes). -> `pick.p_retry_success` = (0.902 - 0.843) / (1 - 0.843) = 0.376.

### RUM: Robot Utility Models
Etukuru et al., "Robot Utility Models: General Policies for Zero-Shot Deployment in New Environments", 2024.
https://arxiv.org/abs/2409.05865

- Table 1 (App. A.1): door opening 47 / 50, drawer opening 47 / 50, tissue pick-up 46 / 50, bag pick-up
  42 / 50, with self-critique retries. -> `pick.p_fail_class` (bag 0.16, tissue 0.08) and, with Dobb-E's
  first-try numbers, `open.p_retry_success`.
- Sec. 3.6, Fig. 11: the MLLM success detector has 4.8 % false positives. -> `verify.p_false_success`
  (silent failures) and `vlm.p_false_yes`.

### DOBBE: Dobb-E
Shafiullah et al., "On Bringing Robots Home", 2023.
https://arxiv.org/abs/2311.16098

- Table 2 (109 tasks in 10 homes, 10 rollouts each, no retries), rows summed by task category: door opening
  79 / 100, drawer opening 50 / 60, door closing 50 / 50, drawer closing 113 / 120. -> `open.p_fail`
  (0.21 / 0.167), `close.p_fail` (0.0 / 0.058), and the first-try part of `open.p_retry_success`.
- Sec. 3.2.3, Fig. 13: demonstrations last 3.82 s on average. Anchor for the assumed `open.duration_s`,
  `close.duration_s`.

### TIDY: TidyBot
Wu et al., "TidyBot: Personalized Robot Assistance with Large Language Models", 2023.
https://arxiv.org/abs/2305.05658

- Table 7, Sec. 4.5: CLIP recognises the category of 95.5 % of 222 egocentric images of household objects.
  -> `find.p_false_positive` = 0.045.
- Sec. 4.5: 15-20 s per object for a pick and a place / toss. -> `pick_place.duration_s`.
- Sec. 4.5: 85.0 % of 240 objects tidied end to end (composition reference).

### BUM: BUMBLE
Shah et al., "BUMBLE: Unifying Reasoning and Acting with Vision-Language Models for Building-wide Mobile
Manipulation", 2024. https://arxiv.org/abs/2410.06237

- Failure analysis, Fig. 6: the wrong object was picked in 10.0 % of trials with 5-10 distractors and
  38.9 % with 20-25 distractors. -> `find.p_wrong_instance` (few / many).

### NAV: Navigating to objects in the real world
Gervet et al., "Navigating to Objects in the Real World", 2022. https://arxiv.org/abs/2212.00922

- Table S3: 5 of the 6 failures of the modular system in 60 real episodes were depth-sensor errors. A
  per-episode count, so only an anchor for the assumed `perception.p_unavailable` and `hw.p_per_sensor_call`.

### ART: Adaptive mobile manipulation for articulated objects
Xiong et al., "Adaptive Mobile Manipulation for Articulated Objects in the Open World", 2024.
https://arxiv.org/abs/2401.14403

- Abstract, Fig. 6: an unadapted behaviour-cloning policy opens novel doors / drawers about 50 % of the time
  (about 95 % after under an hour of online adaptation). -> the `stress` override of `open.p_fail` (0.5).

### CAR: How mobile robots fail in the field
Carlson, "Analysis of How Mobile Robots Fail in the Field", M.S. thesis, University of South Florida, 2004.
https://digitalcommons.usf.edu/etd/980

- Abstract (read at abstract level only; field UGVs, not household robots): 94 % of the failures in a cited
  study suspended the task until repair. -> `hw.p_persistent`.

### STF: Stretch velocities (forum post)
Hello Robot forum, "Physical aspects of the Robot for Simulation", 2023-08-24.
https://forum.hello-robot.com/t/physical-aspects-of-the-robot-for-simulation/792

- Post body: base 0.3 m/s, lift 0.15 m/s, arm 0.4 m/s. -> `move.speed_mps`. Low confidence: a forum post, not
  a datasheet, and the Stretch model is not named.

### S15: Walters et al. 2005 (personal spatial zones)
Walters et al., "The Influence of Subjects' Personality Traits on Personal Spatial Zones in a Human-Robot
Interaction Experiment", IEEE RO-MAN 2005. https://uhra.herts.ac.uk/id/eprint/265/1/101144.pdf

- Table 1: Hall's zones as tabulated (social zone 1.2-3.6 m). -> `move.person_standoff_m` = 1.2 (a move to a
  person stops at the near edge of the social zone).

### Composition references (used in docs/failure_model.md, no parameter)

- SAY: Ahn et al., "Do As I Can, Not As I Say: Grounding Language in Robotic Affordances", 2022.
  https://arxiv.org/abs/2204.01691 - Table 2: execution success 74 % (mock kitchen) and 60 % (real kitchen).
- OVMM: Yenamandra et al., "HomeRobot: Open-Vocabulary Mobile Manipulation", 2023.
  https://arxiv.org/abs/2306.11565 - Table 4: real end-to-end success 15 % (heuristic) and 20 % (RL).
- DYN: Liu et al., "DynaMem: Online Dynamic Spatio-Semantic Memory for Open World Mobile Manipulation", 2024.
  https://arxiv.org/abs/2411.04999 - Sec. 4.2, Fig. 7c: 9 of 17 long-horizon home tasks succeeded.

<!-- BEGIN user-safety sources -->
<!-- END user-safety sources -->

## Assumptions

No source was found for these parameters (research gaps). Each has `assumed: true` and a note saying why
the number was chosen; `anchor:` names the nearest source where there is one. The validator counts and lists
them (`assumed: N params`).

| parameter | value | why / anchor |
|---|---|---|
| `hw.p_per_sensor_call` | 0.002 | no per-call camera / speaker fault rate; an order of magnitude below the motion rate (anchor NAV) |
| `move.p_false_arrival_normal` | 0.01 | CoBot gives only the worst-region rate 0.038 (anchor COB) |
| `move.false_arrival_offset_m` | 0.6 m | above the 0.3 m arrive tolerance so a pose check can detect it |
| `move.p_timeout` | 0.005 | no paper reports timeouts per navigation call |
| `move.fail_time_frac` | U(0.3, 1.0) | time a failed move spends before it reports; modelling choice |
| `perception.p_unavailable` | 0.01 | no per-call dropout rate (anchor NAV Table S3, per episode) |
| `perception.p_clear_on_wait` | 0.5 | no source for recovery of a camera by waiting |
| `find.duration_s`, `look.duration_s`, `vlm.duration_s` | 3-6 s, 3-5 s, 2-4 s | no duration distributions in the sources |
| `handover.p_drop` | 0.0196 | no handover drop rate; BINDER drop-while-placing reused (anchor BIND) |
| `handover.duration_s` | 4-8 s | arm extension and release, no source |
| `open.split`, `close.split` | blocked 0.5 / unreachable 0.5 | no source splits articulated failures by cause; handle failures are reported as unreachable |
| `open.duration_s`, `close.duration_s` | 5-10 s, 4-8 s | anchor DOBBE mean demonstration 3.82 s |
| `close.p_retry_success` | = `open.p_retry_success` | no close-specific retry data |
| `vlm.p_false_no` | 0.05 | no VLM false-negative rate found |
| `grasp_check.p_wrong`, `grasp_check.duration_s` | 0.02, 1 s | no gripper-sensor error rate found |
| `pose.sigma_m`, `pose.duration_s` | 0.05 m, 0.5 s | no home localization noise found |
| `say.words_per_s` | 2.5 | TTS rate, no source opened |
| `ask.timeout_s` | 15 s | how long the robot waits for an answer; design choice |
| `dock.duration_s` | 20-40 s | no source |
| `stress` scaling factor | x2 | R3 methodology sweeps x0.5 / x1 / x2; stress is the x2 end |

User-model and safety assumptions are listed in docs/user_model.md and docs/safety.md (robot-human-safety
part).

## Object provenance (realism)

Used by the catalog's realism fields ([realism.md](realism.md)), not by profile parameters:

- AI2-THOR object types and "Default Compatible Receptacles" (opened 2026-11-02):
  https://ai2thor.allenai.org/ithor/documentation/objects/object-types
- ALFRED: Shridhar et al., "ALFRED: A Benchmark for Interpreting Grounded Instructions for Everyday Tasks",
  2020. https://arxiv.org/abs/1912.01734
- YCB: Calli et al., "Benchmarking in Manipulation Research: The YCB Object and Model Set and Benchmarking
  Protocols", 2015. https://arxiv.org/abs/1502.03143 - Table II: object masses.
