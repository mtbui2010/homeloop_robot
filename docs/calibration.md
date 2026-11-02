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
  no / low / high cleanup. These are per-trial STAGE rates that include causes we inject separately.
- Fig. 4 (page 6, Sankey over all 375 trials, the three cleanup phases pooled): navigation failure 42 =
  35 "localized wrong or no object" (semantic memory) + 7 "navigated to suboptimal final position";
  manipulation failure 73 = 28 hardware + 17 "LangSAM detected wrong object" + 30 AnyGrasp failure
  (the figure labels the model branch 45); placing failure 6 of 260; 254 successes.
  -> `move.p_fail` = Fig. 6 level x 7/42 (motion share only) = 0.0067 / 0.02 / 0.025;
  `pick.p_fail` = Fig. 6 level x 30/73 (grasp-model share only) = 0.0534 / 0.0658 / 0.1027. The share is
  assumed equal at every cleanup level (Fig. 4 pools them). One navigation and one pick stage per trial in
  Fig. 4, so no per-call division. This avoids counting semantic memory (in `find.p_miss`) and hardware
  (in `hw.p_per_motion_call`) twice.
- Sec. III-D: semantic-memory retrieval failure 9.3 % (35 / 375, -> `find.p_miss`) and robot hardware
  failure 7.5 % (28 / 375, -> `hw.p_per_motion_call` = 0.075 / 4 motion primitives per trial). The text
  says 171 pick-and-drop experiments in 10 homes; Fig. 4 counts 375 trials, and 9.3 % / 7.5 % match the
  375 (35 / 375, 28 / 375).
- Sec. III-D ("Robot hardware limitations"): 1 kg payload limit of the robot. -> `carry.payload_kg`,
  `catalog.PAYLOAD_KG`.
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
- Sec. 3.6, Fig. 11: "4.8% of our trajectories exhibit such behavior [a failure judged a success],
  constituting half of the total errors". 4.8 % is a share of ALL trajectories, not of failed ones, and it
  is per task trajectory (one single-skill policy rollout). -> `verify.p_false_success` = 0.048 (the
  unconditional silent-failure probability per manipulation call) and `vlm.p_false_yes` = 0.5
  (P(detector says yes | failed) = 4.8 % / about 9.6 % failed trajectories, "half of the total errors").

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

- Abstract (read at abstract level only; military / USAR field UGVs, not household robots): "Two-thirds of the
  failures examined in [6] and [7] could be repaired in the field"; failures that suspended the task until
  repair were 94 % of the failures reported in [13]. Only an anchor for the assumed `hw.p_persistent` (0.5);
  the 94 % end is kept in the sensitivity sweep below. The full text (USF viewcontent PDF) returned HTTP 403.

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

## Calibration check: OK-Robot pick-and-drop trials

`python -m homeloop_robot.report okrobot --trials 300` runs open-loop pick-and-drop trials in the OK-Robot protocol
(navigate, find, pick, navigate, place; the first failure ends the trial; no retries) on random objects and
surfaces of all houses, `real` profile, and compares the stage of the first failure with OK-Robot Fig. 4.

| stage | OK-Robot Fig. 4 (375 trials) | homeloop_robot `real` (300 trials, seed 0) |
|---|---|---|
| navigation failure (incl. semantic memory) | 11.2 % | 17.0 % |
| manipulation failure (incl. hardware) | 19.5 % | 9.3 % |
| placing failure (incl. the move to the target) | 1.6 % | 18.0 % |
| success | 67.7 % | 55.7 % |

The simulated robot fails more often overall (44 % vs 32 %) and in a different place. Known causes, not tuned
away because no source gives the right per-call numbers: the hardware rate (7.5 % per trial) is spread over all 4
motion calls, whereas Fig. 4 puts all 28 hardware failures in manipulation; the silent-failure rate
`verify.p_false_success` (4.8 %, a per-trajectory rate from RUM) also applies to place, and `carry.p_drop` and
`place.p_drop` (BINDER) apply on the way to and at the target, whereas OK-Robot's drop heuristic failed in 6 of 260
trials; the move to the target is a second navigation that Fig. 4 does not count separately; and the houses have
people, whose presence can stop the robot (safety aborts). Treat the `real` profile as somewhat harsher than
OK-Robot's homes; the `stress` profile is harsher still.

## Hardware faults: transient vs persistent, episode-level rates

`hw.p_per_motion_call` = 0.01875 is sourced (OKR, 7.5 % of 171 trials / 4 motion primitives). The share of
those faults that persist for the episode, `hw.p_persistent`, is **assumed** (0.5). Sources checked for a
transient / persistent split (cleared by retry or restart within the task vs task abandoned / repair):

| source | opened | what it gives | usable? |
|---|---|---|---|
| STR, arXiv 1604.04384 | PDF as text | Sec. 5: crashed components are relaunched automatically (no count). Sec. 6: of 7 runs in 2015, 1 ended by user intervention, 2 by project software bugs, 4 by software or hardware faults beyond the project's components; the 28-day run ended with motors not responding (fixed by firmware). Table 2: recoveries of navigation failures only | no hardware split |
| OKR, arXiv 2401.12202 | PDF as text | Sec. III-D: hardware 7.5 % of trials; Sec. V-A: payload, reach, camera / robot miscalibration "over time", wheels on carpet; no counts per cause and no retries (Sec. V-D: one failed module fails the trial) | no |
| CAR, USF etd/980 | abstract | two-thirds of field failures field-repairable; 94 % of failures in one study suspended the task until repair (military / USAR UGVs) | anchor only |
| Carlson & Murphy, IEEE T-RO 2005 | not opened (paywalled) | - | not used |
| Steinbauer, RoboCup 2012 (doi:10.1007/978-3-642-39250-4_31) | abstract only (Springer full text behind login) | impact classes not critical / repairable / terminal; no number read | not used |
| Honig & Oron-Gilad, Front. Psychol. 2018 (doi:10.3389/fpsyg.2018.00861) | HTML, first part | definitions of terminal and field-repairable failures (citing Carlson & Murphy); MTBF "within a few hours"; no shares | no |
| Wienke & Wrede, arXiv 1708.07379 (developer survey) | PDF as text | Fig. 4 MTBF answers, Fig. 5 hardware the most frequent failure cause; no transient share | no |

Episode-level hardware-failure rate (`python -m homeloop_robot.report hw-rates`), q = 0.01875 per motion call,
n motion calls. "No retry" = P(any hardware fault) = 1 - (1 - q)^n, the episode fails when the planner never
retries (OK-Robot's setting); it does not depend on `hw.p_persistent`. "Retry" = P(the episode is lost to a
persistent fault) when every transient fault is retried until it succeeds, 1 - (1 - q p / (q p + 1 - q))^n.

| `hw.p_persistent` | 4 calls no retry / retry | 8 calls no retry / retry | 12 calls no retry / retry |
|---|---|---|---|
| 0.2 | 7.29 % / 1.51 % | 14.05 % / 3.01 % | 20.32 % / 4.47 % |
| **0.5 (real)** | 7.29 % / 3.73 % | 14.05 % / 7.32 % | 20.32 % / 10.78 % |
| 0.94 | 7.29 % / 6.87 % | 14.05 % / 13.27 % | 20.32 % / 19.24 % |

OK-Robot: 7.5 % per 4-primitive trial with no retry. The 4-call no-retry rate, 7.29 %, matches it (the gap
is the linear split 0.075 / 4; the binomial standard error of 7.5 % on 171 trials is 2.0 points). With
retries, `hw.p_persistent` decides how much of that a recovering planner can win back: half at 0.5.
`stress` scales it x2 to the 0.95 cap, so the stress profile is the persistent end of the sweep.

Calibrated failures vs precondition misuse (`python -m homeloop_robot.report oracle-mix`, seed 0, 300
episodes, random reachable goals, closed-loop oracle `oracle.rollout`, mean 9.1 calls per episode): in `real`,
81.4 % of the oracle's calls succeed and 16.7 % fail with an injected (calibrated) failure: blocked 6.5 %,
timeout 3.5 % (most are `ask` help requests the user does not answer), unreachable 3.0 %, absent 2.2 %,
hw_fault 1.6 %, grasp_failed 1.1 %, dropped 0.3 %, perception_unavailable 0.3 %. The only non-injected
failures are `ask` timeouts from the user model (1.8 %). Episodes: success 78 %, any hardware fault 14 %,
persistent hardware fault 8 % (2 % at p 0.2, 13 % at p 0.94, `--p-persistent`). The selftest trace, which
mixes random calls with unmet preconditions, has a different mix (seed 0, 200 episodes: ok 65.0 %,
unreachable 10.2 %, absent 9.4 %, hw_fault 5.4 %; with the former 0.94: hw_fault 10.9 %), so read
calibrated rates from `oracle-mix`, not from the selftest.

## Assumptions

No source was found for these parameters (research gaps). Each has `assumed: true` and a note saying why
the number was chosen; `anchor:` names the nearest source where there is one. The validator counts and lists
them (`assumed: N params`).

| parameter | value | why / anchor |
|---|---|---|
| `hw.p_persistent` | 0.5 | share of hardware faults that persist for the episode; no household / service source splits transient vs persistent hardware faults (searched below); 0.5 is the maximum-uncertainty value, swept over {0.2, 0.5, 0.94} (anchor CAR) |
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

<!-- BEGIN user-safety sources -->
## Simulated user, ASR and human-aware safety

Sources of `profiles/real/user.yaml` and `profiles/real/safety.yaml`, and of docs/user_model.md,
docs/safety.md and docs/hazards.md. Each source was opened during the research for this repository (PDF or
abstract page). **No ISO, IEC or ANSI standard text was opened** (paywalled; the standards bodies' pages returned
HTTP 403). Every standard value below is as quoted by the secondary source named in the row.

| key | source | link | what was taken (where) | params |
|---|---|---|---|---|
| WHISPER | Radford et al., "Robust Speech Recognition via Large-Scale Weak Supervision", ICML 2023 | https://arxiv.org/abs/2212.04356 | Whisper large-v2 zero-shot WER: FLEURS en 4.4 %, CHiME-6 25.5 %, AMI IHM 16.9 %, AMI SDM1 36.4 % (Table 2) | `asr.en.near_wer`, `asr.en.far_wer`; anchor of `asr.ko.far_cer` (SDM1/IHM ratio 2.154); stress `asr.en.far_wer` |
| KMETEO | Park, Cho, Choo, "Evaluating Automatic Speech Recognition Systems for Korean Meteorological Experts", 2025 (v3) | https://arxiv.org/abs/2410.18444 | KsponSpeech eval-clean CER: Whisper large-v2 zero-shot 14.66 % (Table 3, group 1), fine-tuned 10.48 % (Table 3, group 2) | `asr.ko.near_cer`; stress `asr.ko.near_cer` |
| OLDERVA | Mahmood, Wang, Huang, "Situated Understanding of Errors in Older Adults' Interactions with Voice Assistants: A Month-Long, In-Home Study" | https://arxiv.org/abs/2403.02421 | 2,552 turns of 15 older-adult households: not listened 69, partially listened 29 (Table 2, Sec. 4.1); interruptions 21 (Table 6) | `asr.p_not_heard`, `asr.p_partial`; anchor of `user.p_interrupt_stop` |
| ZOU | Zou, Kanoulas, Liu, "An Empirical Study of Clarifying Question-Based Systems", CIKM 2020 | https://arxiv.org/abs/2008.00279 | answers correct 73.1 % / not sure 9.6 % / incorrect 17.3 % (Table 1, Sec. 3.4); answer time min 1.75 s, mean 7.1 s, median 4.98 s (Sec. 3.3); questions answered before stopping, median 7 (Sec. 3.3, Fig. 2) | `user.answer.p_wrong`, `user.answer.p_not_sure`, `user.latency`, `user.patience_questions`; anchor of `user.p_no_answer` |
| BOHANNON | Bohannon & Andrews, "Normal walking speed: a descriptive meta-analysis", Physiotherapy 97(3), 2011 | https://doi.org/10.1016/j.physio.2010.12.004 | comfortable gait speed by decade and sex; table read from the University of Toronto handout that reproduces it (https://www.physicaltherapy.utoronto.ca/sites/default/files/assets/files/11walking-speed-age-and-sex-specific-normative-values-final.pdf); range 143.4-94.3 cm/s and the short-walk caveat from the abstract | `user.gait_mps_men`, `user.gait_mps_women`; anchor of `user.indoor_gait_factor` |
| STUDENSKI | Studenski et al., "Gait speed and survival in older adults", JAMA 305(1), 2011 | https://doi.org/10.1001/jama.2010.1923 | gait speed mean 0.92 m/s, SD 0.27, 34,485 adults aged 65+ (abstract) | `user.gait_older` |
| WALTERS05 | Walters et al., "The Influence of Subjects' Personality Traits on Personal Spatial Zones in a Human-Robot Interaction Experiment", IEEE RO-MAN 2005 | https://uhra.herts.ac.uk/id/eprint/265/1/101144.pdf | Hall's zones as tabulated: personal 0.45-1.2 m, social 1.2-3.6 m (Table 1) | `safety.personal_zone_m`; anchors of `asr.far_threshold_m`, `user.hearing_range_m` |
| OSKOEI10 | Asghari Oskoei, Walters, Dautenhahn, "An Autonomous Proxemic System for a Mobile Companion Robot", AISB 2010 | https://uhra.herts.ac.uk/id/eprint/13538/2/MohammedrezaEtAl_AISB10Proxemic.pdf | base human-robot distance 57 cm; giving/taking an object -7 cm (Table 1) | `user.approach_distance_m` |
| NIST7851 | Szabo, Shackleford, Norcross, Marvel, "A Testbed for Evaluation of Speed and Separation Monitoring in a Human Robot Collaborative Environment", NISTIR 7851, 2012 | https://doi.org/10.6028/NIST.IR.7851 | separation formula with brake model (Sec. 5); T_R 0.41 s, A 5.0 m/s^2, C_H 0.9 m, C_R 0.25 m, contact threshold 1.15 m, worked example 2.15 m (Sec. 9, printed p. 13); stop + auto-restart and slow override (Sec. 2, 5, 6). Opened at https://nvlpubs.nist.gov/nistpubs/ir/2012/NIST.IR.7851.pdf | `safety.T_r`, `safety.a_max_arm`, `safety.C`, `safety.Z_d`, `safety.Z_r`, `safety.severe_m` |
| NAVARRO21 | Escaida Navarro et al., "Proximity Perception in Human-Centered Robotics: A Survey on Sensing Systems and Applications" (IEEE T-RO) | https://arxiv.org/abs/2108.07206 | SSM constant-speed form S_p = v_h (T_r + T_s) + v_r T_r + S_s + C + Z_d + Z_r; v_h = 1.6 m/s if not monitored; UR10e example 0.236 m (Sec. II, Eq. 1, p. 4) | `safety.v_h_far`; anchor of `safety.mode` |
| PUPA21 | Pupa, Arrfou, Andreoni, Secchi, "A Safety-Aware Kinodynamic Architecture for Human-Robot Collaboration", RA-L/ICRA 2021 | https://arxiv.org/abs/2103.01818 | S_p(t0) (Eq. 4), maximum robot speed toward the person (Eq. 11), green/yellow/red zones (Sec. III, Fig. 1) | formulas in `safety.py` (docs/safety.md) |
| CAMPO19 | Campomaggiore, Costanzo, Lettera, Natale, "A Fuzzy Inference Approach to Control Robot Speed in Human-robot Shared Workspaces", ICINCO 2019 | https://doi.org/10.5220/0007838700780087 | ISO 13855 S = vT + C; operator speed 2.0 m/s, or 1.6 m/s when d > 0.5 m (Sec. 2, Eq. 1, p. 79). Opened at https://www.scitepress.org/Papers/2019/78387/78387.pdf | `safety.v_h_near`; anchor of `safety.v_h_switch_m` |
| HARTMANN26 | Hartmann et al., "Evolution of Safety Requirements in Industrial Robotics: Comparative Analysis of ISO 10218-1/2 (2011 vs. 2025) and Integration of ISO/TS 15066" | https://arxiv.org/abs/2602.17822 | ISO 10218-1:2025 Class I: manipulator mass <= 10 kg, force <= 50 N, speed <= 250 mm/s (cl. 5.1.17, p. 11); PL d / SIL 2 for Class II, PL b / SIL 1 for Class I per ISO 13849-1:2023 and IEC 62061:2021 (p. 12); SSM in ISO 10218-2:2025 Sec. 5.14.5 with the formulas in Annex L (pp. 32-33, Table 12) | anchor of `safety.handover_speed_mps`; docs/safety.md |
| KOAY14 | Koay, Syrdal, Ashgari-Oskoei, Walters, Dautenhahn, "Social Roles and Baseline Proxemic Preferences for a Domestic Service Robot", Int J Soc Robotics, 2014 | https://doi.org/10.1007/s12369-014-0232-4 | handover approach: participants comfortable with the closest distance 0.5 m (Front Close); far pose 1.0 m (abstract; Sec. 2.2.4 p. 9). Opened at https://uhra.herts.ac.uk/id/eprint/4332/1/906788.pdf | `safety.handover_distance_m` |
| STF | Hello Robot forum, "Physical aspects of the Robot for Simulation" (2023-08-24) | https://forum.hello-robot.com/t/physical-aspects-of-the-robot-for-simulation/792 | arm max velocity 0.4 m/s (post body; robot model not named, low confidence) | `safety.arm_speed_mps` |
| FABRICO | Fabrico blog, "ISO 3691-4 driverless industrial trucks" (vendor) | https://www.fabrico.io/blog/iso-3691-4-driverless-industrial-trucks/ | ISO 3691-4 muted personnel-detection speed 0.3 m/s; test pieces (secondary, low reliability) | anchor of `safety.muted_speed_mps` |
| SALVINI21 | Salvini, Paez Granados, Billard, "On the Safety of Mobile Robots Serving in Public Spaces", ACM THRI 10(3), 2021 | https://doi.org/10.1145/3442678 | ISO 13482 clauses 5.6, 5.10.9 and Annex A hazard checklist as quoted (Table 2, p. 7); missing bystander requirements (abstract) | docs/safety.md |
| BELZILE25 | Belzile, Wanang-Siyapdjie et al., "From Safety Standards to Safe Operation with Mobile Robotic Systems Deployment" | https://arxiv.org/abs/2502.20693 | ANSI/RIA R15.08 covers industrial mobile robots, parts 1-3 (Sec. 2, pp. 2-3) | docs/safety.md |
| SNV13482 | SNV abstract of SN EN ISO 13482:2014 | https://connect.snv.ch/en/sn-en-iso-13482-2014 | ISO 13482 scope: mobile servant, physical assistant, person carrier robots; exclusions (abstract) | docs/safety.md |
| EVS12100 | EVS abstract of EVS-EN ISO 12100:2010 | https://www.evs.ee/en/evs-en-iso-12100-2010 | ISO 12100 risk assessment and risk reduction method (abstract) | docs/safety.md (risk register) |
| SAB | Yin, Pang et al., "SafeAgentBench: A Benchmark for Safe Task Planning of Embodied LLM Agents" (v5) | https://arxiv.org/abs/2412.13178 | 10 hazard types (App. A, p. 13) | `hazards.py` codes, docs/hazards.md |
| ROBOGUARD | Ravichandran, Robey, Kumar, Pappas, Hassani, "Safety Guardrails for LLM-Enabled Robots", RA-L 2026 | https://arxiv.org/abs/2503.07885 | rules "Do not harm others", "Don't obstruct exits" (Fig. 1, p. 2) | `hazards.py` codes, docs/hazards.md |
| TRAINS | Heeman & Allen, "Speech Repairs, Intonational Phrases, and Discourse Markers", Computational Linguistics 25(4), 1999 | https://aclanthology.org/J99-4003/ | 23 % of turns contain a speech repair; 671 fresh starts in 6,163 turns (Sec. 1, Table 2) | docs/user_model.md (interruption context) |

### Assumptions (user, ASR, safety)

| param | value | why this number |
|---|---|---|
| `asr.ko.far_cer` | 0.2257 | no Korean far-field number; near CER x English AMI SDM1/IHM ratio 2.154 (WHISPER Table 2) |
| `asr.far_threshold_m` | 1.2 m | outer edge of Hall's personal zone (WALTERS05 Table 1) used as the near/far microphone switch |
| `asr.op_shares` | sub 0.6, del 0.3, ins 0.1 | error-type shares not reported; substitutions taken as the majority |
| `user.p_no_answer` | 0.05 | no silence rate measured; about half of ZOU's not-sure share |
| `user.p_interrupt_stop` | 0.01 / episode | no per-task rate; OLDERVA 21/2,552 turns = 0.82 % rounded |
| `user.interrupt_after_calls` | 1-6 | places a random stop inside a short task |
| `user.gait_child_mps` | 1.0 m/s | no child gait source opened |
| `user.indoor_gait_factor` | 0.7 | BOHANNON warns norms may not hold for short walks with turns |
| `user.motion.rate_per_h` | 2 / h | no in-home movement source |
| `user.motion.pause_s` | 30-300 s | keeps people from walking continuously |
| `user.hearing_range_m` | 3.6 m | outer edge of Hall's social zone (WALTERS05 Table 1); not acoustic |
| `user.p_location_unknown` | 0.2 | location answers useful but not an oracle |
| `user.handover_latency` | median 2 s | no handover-timing source opened |
| `user.handover_timeout_s` | 60 s | engineering default |
| `user.p_unresponsive` | 0.02 | no source |
| `user.asr_on_instruction` | true | benchmark design choice |
| `user.dialog_channel` | app | benchmark design choice: the task and the robot's questions go through the user's app (as the deployed robot_agent dashboard does); `voice` = the robot's speaker and microphone |
| `safety.mode` | monitored | design choice for a robot with a person tracker |
| `safety.v_h_switch_m` | 0.5 m | CAMPO19's wording; the standard's condition could not be checked |
| `safety.v_h_margin` | 0.1 m/s | keeps S_p(0) = 1.191 m inside the houses' 1.20 m path clearance |
| `safety.a_max_base` | 1.0 m/s^2 | no base braking source |
| `safety.handover_speed_mps` | 0.25 m/s | ISO 10218-1:2025 Class I bound as quoted by HARTMANN26; not a handover rule |
| `safety.muted_speed_mps` | 0.3 m/s | ISO 3691-4 value from a vendor blog only (FABRICO) |
| `safety.stop_timeout_s` | 30 s | no source |
| `safety.p_detection_miss` | 0.02 / person / s | no home person-detection benchmark opened |
| `safety.t_r_jitter_s` | 0-0.1 s | no source |
| `safety.p_latency_jitter` | 1.0 (every tick) | no source; the zeroable switch of the latency noise |
<!-- END user-safety sources -->

## Human reach (delivery to a person, round 2)

Sources of `profiles/real/reach.yaml` (docs/reach.md). All were opened (page / table noted).

| key | source | link | what was taken (where) | params |
|---|---|---|---|---|
| CITYU | Online Anthropometry, Ch. 2, forward grip reach (City University of Hong Kong course pages; the underlying survey is not named on the page) | https://personal.cityu.edu.hk/meachan/Online%20Anthropometry/Chapter2/Ch2-34_36.htm | forward grip reach, back of the shoulder blades to the centre of a grasped rod, arm forward at shoulder level, "easy reach without excessive stretch": women 5th / 50th / 95th percentile Hong Kong 580 / 635 / 690 mm, US 655 / 710 / 765 mm, Japanese 570 / 620 / 670 mm (table) | `reach.grip_reach_m` (580 mm) |
| ADEMILUYI24 | Ademiluyi & Aruin, "The effect of advanced age and stool modification on reaching distance in sitting", J Phys Ther Sci 36(11):685-691, 2024 | https://doi.org/10.1589/jpts.36.685 | reach beyond the arm held at ~90 deg, seated, 12 older (70 +/- 4 y) and 12 young adults: forward FlatS old 22.4 / young 26.2 cm, lateral FlatS old 16.8 / young 18.8 cm, footrest forward old 27.9 cm (Table 2). Opened at https://www.jstage.jst.go.jp/article/jpts/36/11/36_2024-013/_article/-char/en | `reach.lean_seated_m` (16.8 cm) |
| BOHANNON17 | Bohannon, Wolfson & White, Physiotherapy 103(4):387-391, 2017 | https://pmc.ncbi.nlm.nih.gov/articles/PMC5628099 | standing Functional Reach Test, older adults, pooled 27.2 cm (95 % CI 25.5-28.9), percentiles 5th 19.4 / 50th 27.2 / 95th 35.0 cm (Table 3) | `reach.lean_standing_m` (19.4 cm) |
| ROSA19 | Rosa, Perracini & Ricci (meta-analysis of the Functional Reach Test), Arch Gerontol Geriatr 81:149-170, 2019 (abstract page) | https://ifp.nyu.edu/?p=1395018 | FRT community-dwelling 26.6 cm (95 % CI 25.14-28.06), non-community (institutional) 15.4 cm (13.47-17.42) | `reach.lean_standing_frail_m` (15.4 cm) |
| ADA | U.S. Access Board, 2010 ADA Standards for Accessible Design | https://www.access-board.gov/ada/ | 308.2.1 forward reach 380-1220 mm above the floor; 308.2.2 high reach over a 510-635 mm deep obstruction 1120 mm max; 902.3 work surfaces 710-865 mm | `reach.band_seated_m` [0.38, 1.12], `reach.band_standing_m` [0.38, 1.22] |
| ICED15 | ICED 2015 reach-envelope paper (arXiv) | https://arxiv.org/abs/1607.04653 | arm length 719 (SD 41.5) mm of 40 adults; reach envelope as an arc of arm length about the shoulder (Table 1, Sec. 4.2) | check of `reach.grip_reach_m` (no parameter) |

`reach.body_offset_m` (0.12 m, from the back of the shoulder blades to the body centre) is **assumed**: no
torso-depth source was opened. Resulting radii: seated 0.58 - 0.12 + 0.168 = **0.628 m**, standing 0.654 m,
standing and frail 0.614 m. The ADA bands are design values for wheelchair users (the seated, reach-limited
case); no standing band for older adults was found, so the ADA band is used for standing people too.

Place-or-hand evidence (motivates mode `reach` as the default, no parameter): in a Stretch user study, all
25 participants who were busy preferred the object placed on their table to a handover, and 77 % when not busy
(Phan & Cosgun, Sensors 25(7):2140, 2025, Table 3, https://pmc.ncbi.nlm.nih.gov/articles/PMC11991642/);
RoboCup@Home 2018 Restaurant: "The robot must place the order on the table. If the robot is not able to do this,
the robot is allowed to hand over the order" (Sec. 6.4, https://athome.robocup.org/wp-content/uploads/2018/10/2018_rulebook.pdf);
OK-Robot drops onto named receptacles in 10 real homes, no handover (https://arxiv.org/abs/2401.12202).
`prefers_handover` (house profile, care_home_suite resident only) has no source: it is a house setting.
