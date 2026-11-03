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
| `answer(question, lang, robot_xy, t, meaning=None) -> (UserReply, Heard)` | `UserReply` = what the person says (`kind`: correct, wrong, not_sure, no_answer, yes, no; `latency_s`); `Heard` = what the robot's ASR returns |
| `help_request(question, t)` | the robot asked for help while a help-clearable fault is active; call it before `answer`; the reply is "OK, I moved it." / "치웠어요." (the robot core clears the fault with its own probability) |
| `hear_instruction(text, lang) -> Heard` | ASR on the spoken task instruction (`app`: near-field; `voice`: near) |
| `hears(person, robot_xy, t, broadcast)` | same room, or within `user.hearing_range_m`; `broadcast` (announce) also reaches adjacent rooms |
| `take_handover(person, obj, t) -> (taken, latency_s)` | the person takes the object after a latency, or does not (unresponsive, asleep, timeout) |
| `people_at(t) -> {id: PersonState}` | positions, velocities, rooms, awake flags |
| `interrupt_plan()` | the scripted `spec.interrupt` or a random stop, as `{after_calls, kind, text, new_goal}`; the runner triggers it at the start of motion call `after_calls + 1` |
| `events_between(t0, t1)` | time-scheduled events; interruptions are call-indexed, so it returns `[]` |

## Dialog channel

`user.dialog_channel` (profile, default `app`) says how the task and the robot's questions travel between the user
and the robot:

- `app` (default): the user gives the task on their phone / tablet app, speaking near its microphone (the
  instruction's ASR is the near-field `app` condition, see ASR below), and the robot's `ask` reaches them there,
  wherever the robot is (`SimUser.reachable`: the user is awake). They answer into the same device (`app` ASR). The
  robot's speaker is not used for the question. This is how the deployed robot_agent runs a task started from its
  dashboard: the question is spoken and listened to in the browser that started the run, and a typed answer from
  any client also answers it (robot_agent `interact/dialog.py`). The user starts each episode at their own seat,
  not next to the robot, so this is the channel that matches the start state.
- `voice`: the robot's own speaker and microphone: a question reaches the user only within hearing range (below),
  and the answer's ASR condition follows the robot-user distance.

`say` and `announce` (messages for other people) always use the robot's speaker and hearing range.
`SimUser.ask_audience(robot_xy, t)` tells the robot who a question reaches; the oracle asks for help with a blocked
path only when the user is reachable.

## Dialog policy

1. **Who answers**: the person with `role: user`. Not reachable (see the channel), asleep, or past the patience
   limit -> no answer (the robot's `ask` times out).
2. **Question type** (`dialog.classify`): a wh-word anywhere (EN which, what, where, who, how, when; KO 어느,
   어떤, 어디, 누구, 뭐, 무엇, 무슨, 어떻게, 몇, 언제) -> `wh`; an EN question starting with an auxiliary or holding a
   "?", a KO sentence ending in 까요?, 나요?, 가요?, 죠?, 니?, 맞아요?, ...요? (also when a remark follows it) ->
   `yes_no`; otherwise `other`.
3. **Mentions**: candidate mentions of the task (`spec.candidates[*].mentions`) and object names (catalog class
   name, colour + name) are matched in both languages after normalization (case, punctuation; Korean spaces
   ignored). Longest match first (R2-6 H2): an occurrence inside a longer name of a different thing of the house,
   one that is not itself also called by the shorter name, does not count, so 냉장고 inside 김치냉장고 and "fridge"
   inside "kimchi fridge" name the kimchi fridge only; "cup" inside "red cup" still names the red cup. A quoted
   either / or ("'A' or 'B'?") naming one candidate is a choice and gets the clarify answer
   (tests/test_dialog_longest_match.py).
4. **Content**, first rule that applies:
   - ASR repair, "could you repeat?" (EN repeat, say that / it again, pardon, come again, didn't catch that; KO 다시
     (한 번) 말씀해, 뭐라고 하셨어요, 한 번 더 말씀해, 잘 못 들었어요) -> the user says it again: right after the request,
     or when the question names the request ("what you'd like me to do", 부탁하신 거), the original request text;
     after an answer of theirs, that answer. ASR noise applies again to what is repeated; people do not get their
     own words wrong, so the correctness mix does not apply (silence and patience still do);
   - "where are you?" (EN where are you / where you are; KO 어디(에) 계세요, 어디세요, and a plain 어디(에) 있어요? that
     names no object, place or person and has no subject before 어디: only an opener such as 지금, 혹시, 그럼,
     죄송한데, 저기요; "그거 어디 있어요?", "말씀하신 물건은 어디 있어요?" ask about a thing, not the listener), naming
     no candidate -> the
     user's own place: "I'm at the sofa." / "소파에 있어요.", or while walking "I'm going to the bed." /
     "침대로 가고 있어요." (`SimUser.place_of`). People do not misstate where they are, so the correctness mix of
     rule 5 does not apply; ASR does;
   - clarification with candidates: a yes/no question naming one candidate -> "Yes, that one." / "네, 맞아요."
     if it is the intended one, else "No, " + the intended answer; a wh question or one naming two or more
     candidates -> the intended answer (`spec.answer`);
   - a scripted resolution (safety clarification, confirming a refused request): any wh or yes/no question ->
     `spec.answer`;
   - ASR repair, "Did you mean X?" (EN did / do you mean / say X, "was it X", "... a typo?"; KO X(이)라고 하셨어요?,
     X 말씀이세요?, X 맞나요?, 오타) where X (a quoted phrase, else the words after "mean" / before 말씀) is a word of
     the user's own request or names an object, place or person of the request -> "Yes. " / "네. " + the request
     restated. This is informative: the wrong / not-sure mix applies (a wrong draw is "not sure", since a "no" would
     deny the user's own words). X that is neither (the misheard word itself) gets no repair answer and falls
     through to the rules below. Never a repair "yes": a choice between quoted phrases in one sentence ("Did you
     mean 'sink' or 'kimchi fridge'?"), and a question that names an object, place, person or task candidate the
     request is not about, by a name that is not a word of the request ("Did you mean 'mug', the red coffee mug?"
     when the blue one is wanted). Those get the clarification / goal answers above and below. Quote marks are
     punctuation when names are matched, so a quoted and an unquoted question get the same answer;
   - a question about the user's own request (when the runner has told the user model what was asked for,
     `SimUser.set_wants(goal)`; `dialog.compose_from_goal`): the user restates what they asked for, never more:
     - "where should I put / bring X?" (EN put, place, bring, take, leave, move, go ...; KO 어디에 두/놓/넣/가져/갖다 ...)
       about an object of the request -> where it goes: "On the sink, please." / "싱크대 위에 놔 주세요.",
       "Bring it to me, please." / "저한테 갖다 주세요.", "Give it to the husband, please."; with "where is it" in the
       same question, its place first;
     - a choice between objects that names the requested one -> "The blue mug."; a choice between places that names
       a place of the request (a destination, the container to open, a place to go, where the person to tell is)
       -> "The sink."; "should I put X on A or B?" / "bring it to you or put it somewhere?" -> where X goes;
     - "where is <a household member>?" -> where they are now ("Grandpa is at the bed."), unless the user does not
       know (`user.p_location_unknown`);
     - a yes / no read-back of the plan ("I will ... Is that right?", "...겠습니다. 맞죠?") -> "Yes, that's right."
       when it states every part of the request (each object with its destination, the containers, the places, the
       person to tell; for "bring it to me" the user's own seat or "you" counts), else "No, " + the first part it
       gets wrong or leaves out ("No, put the blue mug on the sink."); a yes / no question about one part of the
       request is judged on that part only;
     - "what should I do with X?" (X requested) is a destination question; "which place do you mean for X?" too,
       but "which place should I look for X?" asks where X is;
     - a list of places none of which is where the request goes, when the request is for a person -> who it is
       for: "Bring it to me, please." or where that person is ("Grandpa is at the bed.");
     - "어디에 가져다줘야 할까요?" (Korean drops the object) / "Where should I put it?" with one thing asked for
       (or all going to the same place) -> where it goes; an empty slot ("Where should I put the ?") is not
       answered;
     - open questions ("What should I do?", "What else?") are not answered from the request;
   - "where is X?" about one object -> its true place ("It's on the counter." / "조리대 위에 있어요."), unless the
     user does not know (`user.p_location_unknown`); "where should I put X?" is not read as "where is X?";
   - otherwise "I'm not sure what you mean." / "무슨 말씀인지 잘 모르겠어요." (the generic user: "I don't know.").
5. **Correctness mix** on informative answers: wrong with `user.answer.p_wrong` = 0.173 (another candidate,
   a flipped yes/no, another place, or `spec.wrong_answer`; when no alternative exists the user is unsure
   instead; "another place" is a surface or container where an object of the task is usually kept, a catalog
   typical receptacle that fits it (realism R-b), as people confuse one usual place for another, never the
   wardrobe for a mug: `SimUser.wrong_places`), not sure with `user.answer.p_not_sure` = 0.096, else correct (73.1 %). ZOU Table 1: crowd workers
   answering a product-search system's clarifying questions, the closest measured answer mix we found (it is not
   a robot study).
6. **Silence**: `user.p_no_answer` = 0.05 (assumed; no measured rate).
7. **Patience**: after `user.patience_questions` = 7 questions (ZOU Fig. 2 median) the user stops answering.
8. **Latency**: lognormal, median 4.98 s, sigma 0.842 (from mean 7.1 s), floor 1.75 s (ZOU Sec. 3.3).
9. **Language**: the user answers in the episode language.

## Structured questions

A planner may attach a **meaning** to a question: `ask(question, lang, meaning={"qtype": ..., <slots>})`. The
user then picks the answer from the task script by qtype and slots (`homeloop_robot/intent.py`,
`answer_structured`) instead of reading the text. The question text is still what the user hears: it is logged as
the robot's utterance, and the answer goes through the same correctness mix (rule 5), silence, patience, latency
and ASR noise as any answer. The meaning never changes the outcome draws of the call (it is not part of the
outcome key). The qtype list is frozen:

| qtype | slots | what the question asks | the answer from the script |
|---|---|---|---|
| `which_object` | `options` (the things offered), `obj` | which object the user means or wants ("Which one, the white mug or the green mug?", "What should I bring?") | the intended candidate (`spec.answer`) of an object clarification; else the requested object ("The red book.") |
| `which_place` | `options` (places offered), `obj` (the thing to be placed), `verb` (`open` / `close`: which container or door) | which place, or where something should go or where the robot should go ("Where should I put the mug?", "Which shelf do you mean: A or B?", "What should I open?") | the intended candidate of a destination clarification; with `verb`, the container the request opens / closes ("The fridge."); else where the object goes, the place the request names, or "anywhere in the bedroom" for a room |
| `confirm` | `goal` (a read-back sentence) or `obj` | a yes / no check of the robot's reading: its plan ("I will ... Is that right?") or one thing ("Is it the red mug?") | rule 4's yes / no on a candidate, or the read-back check ("Yes, that's right." / "No, put the blue mug on the sink.") |
| `where_are_you` | - | where the user is now | the user's place, or where they are walking to (not informative) |
| `where_is` | `obj` (required: an object or a person) | where an object or another person is now | its true place, unless the user does not know |
| `repeat` | `about`: `request` or `answer` | say the request or the last answer again, or restate the task ("Could you repeat that?", "What should I do exactly?") | the request text, or the user's last answer (ASR again; not informative) |
| `did_you_mean` | `word` (required) | a check of a word the robot may have misheard in the user's own words | "Yes. " + the request restated when the word is the user's own; else a `confirm` of that thing |
| `what_to_say` | `person` | what message to give someone | the message of the request's `said_to` (catalog `MESSAGE_TEXT`) |
| `help` | - | a request to clear the way / help with an obstacle | with a help-clearable fault, "OK, I moved it." (as for HELP_RX questions); else "not sure" |
| `free` | - | none of these | the text is read by the rules (below) |

Unknown qtypes, wrong slot types or a missing required slot make the meaning void (`intent.clean`): the text is
read as free text. A qtype whose script has nothing to say gets "not sure" like an unanswerable question.

**Free text** (no meaning, or `free`), in this order:

1. **Rules**, first the reading conventions of spoken dialog (`intent.read_free`), then `dialog.compose` (dialog
   policy above) on the part of the question that is answered (`intent.text_for_rules`). The conventions:
   1. the robot's own re-ask preamble ("Sorry, I didn't hear you.", "Sorry, I may have misheard you.",
      "죄송해요, 잘 안 들렸어요.") is not a request to repeat, and a context sentence ("You mentioned the X.",
      "X 얘기하셨죠?") is not the question: the question after it is read; neither is the robot's remark on what is
      not in its plan when a translation turns it into a question with another question after it ("김치냉장고 얘기가
      제 계획에 없나요? 제가 우유를 주방 냉장고에 두겠습니다. 맞죠?" -> the read-back is answered; pilot round 3,
      `tests/test_dialog_pilot_r3.py`);
   2. a compound question is answered from its **first** question ("Where is the red book, and where should I
      bring it to?" -> where it is); sentences before the first "?" are context (a read-back); a Korean list of
      steps ("A하고, B하고, ... 맞나요?") is one question;
   3. an open "what should I do (there)?", "which things ... and where?" with nothing specific named, or "what
      should I do with X?" where X names nothing in the house -> `repeat` (the user says the task again); "what
      does 'X' mean?" about a short quoted word -> `did_you_mean`;
   4. "Where is X?" naming a thing or person of the house (also after "I couldn't find X.") -> `where_is`;
      "which drawer / 어떤 서랍", a choice between two places, "어디에 둘까요?" -> `which_place`; a choice between
      two things -> `which_object`; one proposal ("Should I ...?", "...드릴까요?") or a read-back with a tag
      ("맞죠?", "Is that right?") -> `confirm`; "What should I tell X?" -> `what_to_say`; a remark with no
      question, or a request for the user to do the task ("Can you bring me the mug?") -> `free` (not sure).
   When a rule answers, that is the answer (path `rules`).
2. **LLM classifier**, only when the rules do not understand the question (rule `not_understood` /
   `generic_user`) and the run has an LLM: `homeloop_bench/user_intent.py` maps the question (preamble removed)
   onto the qtype list plus slots with a fixed prompt (version `ui2`: the qtype list with examples and the same
   reading conventions), temperature 0, seed 0, JSON output. It only classifies; the answer comes from
   `answer_structured` (path `llm`). A `free` or unusable classification keeps "not sure".
3. Classifications are cached per run in `<out>/llm_cache/user_intent.jsonl`, so a rerun gives the same
   episodes. With no LLM (or `--llm fake`, or `HOMELOOP_USER_CLASSIFIER=rules`) only the rules apply
   (`summary.json` config `user_classifier: rules`).

**A meaning about nothing.** A `which_object` / `which_place` meaning whose `obj` names nothing in the house
(SAGE's "What should I do with the chicken bring?" about an ASR fragment) cannot be answered about that thing: a
"where ...?" question keeps `which_place` without the object, otherwise the user says the task again (`repeat`)
(`intent.ungrounded`).

**Heard-text check: the meaning must match what the user hears** (both languages; R2-7 note, review round 1).
No real user hears a planner's meaning, only its text. A meaning counts only when the text the user hears says it
(`SimUser._content`):

1. the text is in the user's language (`intent.in_lang`): a Korean household member does not follow a question
   that is mostly English (more words in Latin letters than words with Hangul: robot_agent's `_in_lang` returns the
   English when its translation call fails, also under its LLM budget), an English one not a question that is
   mostly Korean. Such a question is answered "I'm not sure what you mean." (rule `not_in_lang`), with or without a
   meaning. This is a documented assumption: some Korean users follow simple English, but the robot cannot count
   on it;
2. the text, read by the free-text chain above (rules, then the classifier), gives the same qtype;
3. the slots name the same things, places and people as the text (`intent.slots_agree`): they disagree when, for
   one kind, the slots name something the text does not and the text names something the slots do not ("빨간 사과
   어디 있어요?" with `obj: remote`; a read-back naming the sofa with a `goal` naming the TV stand; options naming
   other places), or when a thing / person slot names nothing of the house while the text names a thing or a
   person ("plates" for "접시 어디 있어요?"). A text that names nothing of that kind ("Where should I put it?") or
   fewer of them agrees (context).

Otherwise the user answers what it heard (that reading, or "not sure") and the answer is recorded with path
`structured_mismatch` ("Where are you?" translated as "여기 있어요?" is not a question about the user's position;
`{"qtype": "what_to_say"}` sent with the text "Okay." gets no message). The adapter derives SAGE's meanings from
its English templates, so in English episodes the user hears the template itself; the rules read every SAGE
template as the qtype the adapter gives it (test `test_sage_english_templates_read_as_their_meaning`), so a
faithful question is never rejected. To read those templates, the rules also read a request for help with an
obstacle ("Please clear the way and say yes.", "가장자리 쪽으로 옮겨 주세요") as `help`, "Please answer yes or no." as
`repeat` (`about: answer`), "Could you say the task in other words?" as `repeat`, and a where-should-it-go
question they cannot answer ("Where should I put the ?", "Where should I go?") as `which_place`
(`intent.read_surface`). The share of `structured_mismatch` answers is in each run's `summary.json` `dialog_paths`
(one language per run); questions not in the user's language are the answers with rule `not_in_lang`.

A read-back (`confirm` with a `goal`) is also answered for the sentence heard: when the heard read-back states something (it names a thing, place or person
of the house, quotes a message, or, in Korean, holds a word in Latin letters such as a raw id) and the user's yes /
no to it differs from the yes / no to the meaning's English read-back, the answer is the one to the heard sentence
(path `structured_mismatch`). A Korean translation that names fewer things than the English ("…주방에 놓겠습니다"
for "…on you", "파트너B에게" for "to husband") passes the slot check above, but the user agrees or disagrees with
what they heard (pilot round 1, hl-dev-000010 / 000013). A read-back that states nothing ("그렇게 할게요. 맞죠?")
is taken from context (`intent.vague_read_back`).

The same assumption holds for messages: a `said_to` goal counts only for an utterance in the household's language
(the episode's, `World.lang`): "Dad, lunch is ready." said in English in a Korean home does not tell dad
(docs/world.md).

Every answered question records how it was read: `SimUser.log[*]` and the episode's `calls[*].intent` hold
`{path: structured | structured_mismatch | rules | llm, qtype, rule}`, `episodes.jsonl` has `dialog_paths` (counts) and `summary.json`
has `dialog_paths` (shares). For a rules answer the qtype is the one its rule implies (`intent.rule_qtype`).

**Who declares a meaning.** `oracle`: its gold clarification question (`which_object` / `which_place`, the
candidates as options) and its help request (`help`). `knowno_like`: its choice question (`which_object`, or
`which_place` when the options differ only in a place). `naive` never asks. robot_agent's SAGE-v2 (AssistLoop)
writes every question in English from fixed templates and translates it just before its Ask skill; the bench
adapter wraps `AssistLoop._ask_io` on the loop instance (robot_agent is not edited), sees the English question,
and `homeloop_robot/configs/ra_dialog.py` (`derive`) maps it onto its template id, qtype and slots (read-back ->
`confirm` with the read-back sentence; "Which place do you mean: A or B?" -> `which_place`; "Where are you?
Which place should I bring it to?" -> `where_are_you`; "I couldn't find the X. Where is it?" -> `where_is`;
"What should I open / close?" (understand.issue_question's verb issue, only robot_agent's verbs open / close /
shut) -> `which_place` with `verb`; ...;
the list and the robot_agent function each comes from are in that file). Questions the understanding LLM writes
itself, and robot_agent's ClosedLoop planners (grace, llm_direct), have no template: free text.
`HOMELOOP_RA_STRUCTURED=0` turns the adapter's meanings off (ablation).

**Accuracy audit** (`python -m homeloop_bench.sim_user_audit`; result `homeloop_bench/data/quality/sim_user_audit.json`).

- *Set* (fixed, `homeloop_bench/data/quality/sim_user_audit/questions.jsonl`): 533 real robot questions (266 EN, 267
  KO) taken from the runs: live_smoke sage EN/KO (282), the R2-6 sage traces (183), with 313 questions of
  tasks in the sage failure analysis tagged by their `causes.tsv` cause (`context.hard_case`), exp_r2 oracle (61) and progprompt_like (5), and the early R2-5 probe (2). Each row has
  the task id and, for a Korean sage question, the English question SAGE wrote before translation (`robot_en`,
  from the translation prompt in the trace or the run's LLM cache; one untranslated English question is its own
  English).
- *Gold*: three independent agent judges labelled every question with a qtype and slots from what the person
  hears (`labels_{1,2,3}.json`). Gold is the qtype of at least two judges; the 4 questions where all three differ
  are listed in `disagreements` and left out (`n_disagree_excluded`).
- *Simulator reading*: each question goes through the chain of an episode of its task (profile ideal, seed 0):
  structured (the meaning the run's planner attached, rebuilt the way the run built it: SAGE's template via
  `configs/ra_dialog.derive`, the oracle's gold question or help request, none for the others), the heard-text
  check (both languages), rules, then the classifier (qwen3-vl:8b-instruct on GPU 0, cached in
  `sim_user_audit/user_intent_cache.jsonl`, so the audit reruns without a server).
- *Score*: a reading is correct when its qtype is gold and, for each key slot both sides give (where_is `obj`,
  did_you_mean `word`, repeat `about`, what_to_say `person`, which_place `obj` and `options`, confirm `goal` and
  `obj`), the simulator's value matches a gold judge's value: same words, or naming the same object of the house;
  for `options` and a read-back `goal`, naming the same objects, places and people of the house (one in common, no
  kind where each names one the other does not). A gold value that names nothing of the house (a word the
  translation made up, "부두" for the dock) cannot be compared and is not checked. The slots scored are those of
  the reading the answer came from (the meaning, or the heard text's reading for `structured_mismatch`); a
  reading by a rule of `dialog.compose` has no slots: only its qtype counts. `key_slots.by_slot` has the counts.
- *Untranslated Korean questions*: a question of a Korean episode that is not in Korean (3 in the set: "I
  couldn't find the cooking pot. Where is it?", ...) is not followed by the Korean user by design (above); the
  judges' label is its English meaning, which the user never gets, so these are left out of the accuracy and
  listed in `untranslated_ko` with the simulator's answer.

| | n | accuracy | EN | KO | structured | rules | llm | structured_mismatch |
|---|---|---|---|---|---|---|---|---|
| before the fixes (robot a3e97d7, bench 5215e4c; prompt ui1) | 529 | 0.758 | 0.788 | 0.728 | 0.913 (61 %) | 0.503 (27 %) | 0.540 (12 %) | - |
| after (prompt ui2) | 529 | 0.953 | 0.966 | 0.940 | 0.985 (63 %) | 0.917 (27 %) | 0.829 (7 %) | 0.867 (3 %) |
| review round 1: heard-text check in both languages, slot agreement, more key slots, untranslated KO left out | 526 | **0.954** | **0.962** | **0.947** | 0.991 (60 %) | 0.917 (27 %) | 0.788 (6 %) | 0.938 (6 %) |
| pilot round 1: a read-back is confirmed or corrected for the sentence heard | 526 | **0.954** | **0.962** | **0.947** | 0.990 (59 %) | 0.917 (27 %) | 0.788 (6 %) | 0.951 (8 %) |

(accuracy of each path, with its share of the scored questions). Review round 1 also scores which_place `obj` /
`options` and confirm `goal` / `obj` (340 key slots checked, 338 matched); the structured_mismatch answers are now
all Korean questions (32), none English. Pilot round 1 moved 9 Korean read-backs from structured to
structured_mismatch (now 41; 339 key slots checked, 337 matched): their Korean translation drops or changes the
destination ("욕실 주니어 캐비닛", "kimchi_fridge에"), and the answer is now the one to that sentence; the qtype
accuracy is unchanged. The rules added in that round to read SAGE's own templates (help, yes /
no again, where-should-it-go, a leading "Where are you?") were written while reading this set's English
structured questions, so they too are in-sample. The fixes were made from this set's confusions:
the conventions above, SAGE's "You mentioned the X. What should I do there?" read as `repeat` (it was `free`),
the Korean heard-text check (R2-7 note) and prompt ui2. The set was not changed (no question was dropped or
relabelled), but the result is an in-sample number: the conventions were written while reading these errors, so
accuracy on new robot questions may be lower. The before row is the same set and scorer run on the code before
the fixes (`sim_user_audit/baseline.json`). Remaining confusions after the fixes (25 of 529): mostly an English or
Korean question that offers an action and a place in one sentence ("Should I bring the blue book to the bed, or
do you want me to hold them there?": gold which_place, read as a proposal), robot remarks the judges call `free`
but the rules read as a proposal, and English slots that name an object by another word ("plates" for 접시). The
oracle's episodes (50 dev tasks, real, seed 0, EN and KO) are unchanged by the fixes.

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
| app (near-field: the user's phone / tablet) | 0.044, Whisper large-v2 FLEURS en (WHISPER Table 2) | 0.0521 = Speech-MASSIVE ko-KR CER 8.04 % (SMASSIVE Table 1) x KsponSpeech sWER/WER 0.648 (KSPON Table 3), meaning-changing errors only, assumed |

With `user.dialog_channel = app` (the default) the instruction and the answers use `app`. With `voice` the
answer condition depends on the distance between the robot and the speaker, and the instruction is spoken from
`user.approach_distance_m` = 0.57 m (OSKOEI10 Table 1), so it is near.

Share of instructions that reach the planner changed (`python -m homeloop_robot.report asr-share --tasks
<bench dev.jsonl>`, real, seed 0, 1,000 dev tasks; details and the old value in
[calibration.md](calibration.md#near-field-asr-app-channel-round-2)):

| lang | any change | an entity changed |
|---|---|---|
| EN (18.1 words) | 58.1 % | 18.8 % |
| KO (30.1 syllables) | 76.5 % (was 91.9 % with the near rate; 88.5 % corrupted) | 35.1 % (was 56.9 %) |
 `stress` uses zero-shot Korean (0.1466,
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
- SMASSIVE: https://arxiv.org/abs/2408.03900
- KSPON: https://ksp.etri.re.kr/ksp/article/file/62525.pdf
- SLURP: https://arxiv.org/abs/2011.13205
- OLDERVA: https://arxiv.org/abs/2403.02421
- ZOU: https://arxiv.org/abs/2008.00279
- BOHANNON: https://doi.org/10.1016/j.physio.2010.12.004 (decade table read from https://www.physicaltherapy.utoronto.ca/sites/default/files/assets/files/11walking-speed-age-and-sex-specific-normative-values-final.pdf)
- STUDENSKI: https://doi.org/10.1001/jama.2010.1923
- WALTERS05: https://uhra.herts.ac.uk/id/eprint/265/1/101144.pdf
- OSKOEI10: https://uhra.herts.ac.uk/id/eprint/13538/2/MohammedrezaEtAl_AISB10Proxemic.pdf
- TRAINS: https://aclanthology.org/J99-4003/
