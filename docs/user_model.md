# Simulated user

`homeloop_robot/user.py` (`SimUser`), `dialog.py` (what the user means to say) and `asr.py` (what the robot hears)
simulate the people of a house: they answer the robot's questions in English or Korean, sometimes wrongly,
vaguely or not at all; the robot mishears them; they walk between seats; they take handed-over objects or do not;
and they can interrupt a task. Parameters: `homeloop_robot/profiles/real/user.yaml`. Sources and assumptions:
[calibration.md](calibration.md) (user-safety block). The people's positions feed the safety monitor
([safety.md](safety.md)).

All randomness comes from the episode's seeded streams (`streams.rng_for("user", ...)`), keyed by what happens
(the n-th question, the n-th handover, the person's motion), never by wall-clock time. The same episode key and
seed give the same answers, walks and ASR errors.

## Interface (`UserModel`)

| method | what it does |
|---|---|
| `SimUser(world, profile, streams, lang, spec)` | `lang` = episode language (`en`/`ko`); `spec` = the task's `user` block (persona, candidates, answer, interrupt, optional `wrong_answer`, `asleep`); `None` = a generic user |
| `answer(question, lang, robot_xy, t) -> (UserReply, Heard)` | `UserReply` = what the person says (`kind`: correct, wrong, not_sure, no_answer, yes, no; `latency_s`); `Heard` = what the robot's ASR returns |
| `help_request(question, t)` | the robot asked for help while a help-clearable fault is active; call it before `answer`; the reply is "OK, I moved it." / "치웠어요." (the robot core clears the fault with its own probability) |
| `hear_instruction(text, lang) -> Heard` | ASR on the spoken task instruction (near condition) |
| `hears(person, robot_xy, t, broadcast)` | same room, or within `user.hearing_range_m`; `broadcast` (announce) also reaches adjacent rooms |
| `take_handover(person, obj, t) -> (taken, latency_s)` | the person takes the object after a latency, or does not (unresponsive, asleep, timeout) |
| `people_at(t) -> {id: PersonState}` | positions, velocities, rooms, awake flags |
| `interrupt_plan()` | the scripted `spec.interrupt` or a random stop, as `{after_calls, kind, text, new_goal}`; the runner triggers it at the start of motion call `after_calls + 1` |
| `events_between(t0, t1)` | time-scheduled events; interruptions are call-indexed, so it returns `[]` |

## Dialog policy

1. **Who answers**: the person with `role: user`. Not in hearing range, asleep, or past the patience limit ->
   no answer (the robot's `ask` times out).
2. **Question type** (`dialog.classify`): a wh-word anywhere (EN which, what, where, who, how, when; KO 어느,
   어떤, 어디, 누구, 뭐, 무엇, 무슨, 어떻게, 몇, 언제) -> `wh`; an EN question starting with an auxiliary or ending in
   "?", a KO question ending in 까요?, 나요?, 가요?, 죠?, 니?, 맞아요?, ...요? -> `yes_no`; otherwise `other`.
3. **Mentions**: candidate mentions of the task (`spec.candidates[*].mentions`) and object names (catalog class
   name, colour + name) are matched in both languages after normalization (case, punctuation; Korean spaces
   ignored).
4. **Content**, first rule that applies:
   - clarification with candidates: a yes/no question naming one candidate -> "Yes, that one." / "네, 맞아요."
     if it is the intended one, else "No, " + the intended answer; a wh question or one naming two or more
     candidates -> the intended answer (`spec.answer`);
   - a scripted resolution (safety clarification, confirming a refused request): any wh or yes/no question ->
     `spec.answer`;
   - "where is X?" about one object -> its true place ("It's on the counter." / "조리대 위에 있어요."), unless the
     user does not know (`user.p_location_unknown`);
   - otherwise "I'm not sure what you mean." / "무슨 말씀인지 잘 모르겠어요." (the generic user: "I don't know.").
5. **Correctness mix** on informative answers: wrong with `user.answer.p_wrong` = 0.173 (another candidate,
   a flipped yes/no, another place, or `spec.wrong_answer`; when no alternative exists the user is unsure
   instead), not sure with `user.answer.p_not_sure` = 0.096, else correct (73.1 %). ZOU Table 1: crowd workers
   answering a product-search system's clarifying questions, the closest measured answer mix we found (it is not
   a robot study).
6. **Silence**: `user.p_no_answer` = 0.05 (assumed; no measured rate).
7. **Patience**: after `user.patience_questions` = 7 questions (ZOU Fig. 2 median) the user stops answering.
8. **Latency**: lognormal, median 4.98 s, sigma 0.842 (from mean 7.1 s), floor 1.75 s (ZOU Sec. 3.3).
9. **Language**: the user answers in the episode language.

## ASR

Per utterance: not heard with `asr.p_not_heard` = 0.027 and partly heard with `asr.p_partial` = 0.0114 (the first
half or more of the words survive) (OLDERVA Table 2: 69 and 29 of 2,552 in-home turns of older adults);
otherwise each English word / Korean syllable is corrupted with the WER / CER of the condition: a substitution,
a deletion, or an inserted short function word (EN the, a, and, to, it; KO 이, 요, 그), in shares 0.6 / 0.3 / 0.1
(assumed). Substitutions are always plausible recogniser output, never non-words: an English word becomes a
hand-listed near-homophone (cup -> cop, kitchen -> chicken) or the nearest real word of a ~330-word vocabulary by
edit distance; a Korean syllable becomes a neighbouring-vowel or changed-final-consonant syllable (컵 -> 캅)
restricted to the 2,350 common syllables of KS X 1001.

| condition | English WER | Korean CER |
|---|---|---|
| near (<= 1.2 m) | 0.044, Whisper large-v2 FLEURS en (WHISPER Table 2) | 0.1048, Whisper large-v2 fine-tuned on KsponSpeech (KMETEO Table 3) |
| far | 0.255, Whisper large-v2 CHiME-6 homes (WHISPER Table 2) | 0.2257 = 0.1048 x 2.154 (AMI SDM1/IHM ratio, assumed transfer) |

The answer condition depends on the distance between the robot and the speaker; the instruction is spoken from
`user.approach_distance_m` = 0.57 m (OSKOEI10 Table 1), so it is near. `stress` uses zero-shot Korean (0.1466,
KMETEO Table 3 group 1) and the AMI single-distant-microphone English rate (0.364).

## Motion

Each person walks between their own seats and the house's seat places: departures are a Poisson process with
`user.motion.rate_per_h` = 2 per hour (assumed) and at least a pause of 30-300 s (assumed); the path is the
house's door-aware path; the speed is the person's gait speed x `user.indoor_gait_factor` = 0.7 (assumed;
BOHANNON warns its norms may not hold for short walks with turns):

- adults under 65: comfortable gait by decade and sex (BOHANNON decade table, e.g. women 30-39 1.34 m/s);
- 65 and over: drawn once per episode from Normal(0.92, 0.27) m/s (STUDENSKI), truncated at mean +- 2.5 SD;
- children: 1.0 m/s (assumed; no child source).

In `ideal` people do not move. A person's body at a seat other than the starting one is 0.5 m beyond the seat's
approach pose (or the place's `body_pos` when the house gives one).

## Handover, interruptions

Handover: the person takes the object after a lognormal latency (median 2 s, assumed); with
`user.p_unresponsive` = 0.02 (assumed), or when asleep, or if the latency exceeds `user.handover_timeout_s` =
60 s, the handover times out.

Interruptions: tasks of capability `correction` script one (`spec.interrupt`); in addition, with
`user.p_interrupt_stop` = 0.01 per episode (assumed; anchor OLDERVA, 21 interruptions in 2,552 turns) the user
says "Stop, please stop." / "잠깐, 멈춰 주세요." after a uniform 1-6 motion calls. Spoken self-repairs are very
common in task dialogue (23 % of turns contain one, TRAINS), which is why corrections are part of the benchmark;
we found no per-task rate for a user changing the goal while a robot works.

## Consistency check

`user.consistency(world, profile, n, seed, lang)` and `asr.consistency(profile, n, seed)` run n seeded draws and
return one row per parameter (`param, expected, observed, n, lo, hi, ok`): the empirical rate must lie in the
99.9 % binomial interval of the profile value (DESIGN 13.3). Rows: `user.p_no_answer`, `user.answer.p_wrong`,
`user.answer.p_not_sure` (per answered question), `asr.p_not_heard`, `asr.p_partial` (per utterance) and the four
WER/CER values (per heard word or syllable). `python -m homeloop_robot.profiles consistency` includes them.
With n = 20,000 every row passes for `real` and `ideal` in both languages.

## What the user model is not

It is not a language model: it answers only what its rules and the task's `user` block cover, so a planner
cannot extract the goal by asking open questions; a vague question gets "not sure". Elderly-specific ASR rates
(read speech, fine-tuned models) were found but not used, because they are lower than the in-home breakdown
rates of OLDERVA.

## Sources

Full entries in [calibration.md](calibration.md).

- WHISPER: https://arxiv.org/abs/2212.04356
- KMETEO: https://arxiv.org/abs/2410.18444
- OLDERVA: https://arxiv.org/abs/2403.02421
- ZOU: https://arxiv.org/abs/2008.00279
- BOHANNON: https://doi.org/10.1016/j.physio.2010.12.004 (decade table read from https://www.physicaltherapy.utoronto.ca/sites/default/files/assets/files/11walking-speed-age-and-sex-specific-normative-values-final.pdf)
- STUDENSKI: https://doi.org/10.1001/jama.2010.1923
- WALTERS05: https://uhra.herts.ac.uk/id/eprint/265/1/101144.pdf
- OSKOEI10: https://uhra.herts.ac.uk/id/eprint/13538/2/MohammedrezaEtAl_AISB10Proxemic.pdf
- TRAINS: https://aclanthology.org/J99-4003/
