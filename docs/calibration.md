# calibration

To be written (robot-core stream).

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
