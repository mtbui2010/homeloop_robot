# Reach and delivery to a person

Round 2 changes what "bring me X" means. A home robot usually puts the object down on a surface the person
can reach from where they sit or stand; it hands it over only when it has to. The code is
`homeloop_robot/reach.py`; the parameters are `profiles/real/reach.yaml`; the sources are in
[calibration.md](calibration.md#human-reach-delivery-to-a-person-round-2).

## Goal atom

```json
{"pred": "delivered", "args": ["mug_1", "grandma"], "mode": "reach", "mode_reason": null}
{"pred": "delivered", "args": ["mug_1", "grandma"], "mode": "hand", "mode_reason": "explicit"}
```

Text form (`goals.parse` / `goals.format`): the mode in square brackets right after the predicate name and
before the argument list, e.g. `delivered[reach]` applied to `(mug_1, grandma)`. `mode_reason` is `null` for `reach` and one of `explicit`,
`no_surface`, `user_needs` for `hand`. It records why the task needs a handover; scoring does not read it.
`held_by(obj, person)` still parses and means the same as `delivered[hand]`, so old data keeps working.

| mode | holds when |
|---|---|
| `hand` | the object is in the person's hand (`obj.at == "person:<id>"`, after a completed `handover`) |
| `reach` | the object is in the person's hand, **or** it rests on a support surface the person can reach |

`reach.delivered(world, obj, person, mode)` implements both, and `goals.holds` calls it.

## The reach predicate

`reach.reachable(obj, person, world)` is true when the object is in the person's hand, or when all of
these hold:

1. it lies on a **support surface**: a `surface` place whose type is `table`, `desk`, `counter`,
   `nightstand` or `shelf` (`reach.surface_type`). A seat, a bed, the floor, a stove, a sink, a drying rack,
   a TV stand and the inside of a container never count;
2. the surface is in the room the person is in;
3. the surface height is inside the band for the person's **posture**: seated 0.38-1.12 m, standing
   0.38-1.22 m (ADA 308.2.1 / 308.2.2). A 1.45 m shelf is out of reach, and so is the floor;
4. the horizontal distance from the person's body centre to the object's spot on the surface
   (`reach.surface_xy`: the place's `top` in the house YAML, or 0.5 m ahead of the approach pose) is at most
   R(posture):

   R = `reach.grip_reach_m` - `reach.body_offset_m` + lean

   | posture | lean | R |
   |---|---|---|
   | seated | `reach.lean_seated_m` 0.168 m (lateral seated reach of older adults) | 0.628 m |
   | standing | `reach.lean_standing_m` 0.194 m (5th percentile standing FRT, older adults) | 0.654 m |
   | standing, `frail: true` | `reach.lean_standing_frail_m` 0.154 m (institutional FRT) | 0.614 m |

   Grip reach is 0.58 m (5th percentile of Hong Kong women, CITYU). `reach.body_offset_m` = 0.12 m is
   assumed (no torso-depth source).

These are geometry parameters with role `nominal`, so `ideal`, `real` and `stress` use the same values.

### Posture and position over time

`reach.person_pose(world, pid)` reads where the person is **now**. The robot copies the user model's
positions into `world.people_now` after every call (`Robot.sync_people`).

- A person who is not walking and is within 0.35 m of a seat's body position (`person_pos`) is `seated`
  there. A bed counts as a seat (sitting up in bed). A person whose usual place is a desk or a table sits at it.
- Everyone else is `standing`: at a stand spot (`kind: stand`, e.g. `front_door@entrance`), anywhere else,
  and always while walking.

Delivery is judged **where the person is when the episode ends**. If the person walks away after the object
was put down, a `reach` delivery that was within reach can fail. This is intended: they asked for the object
to come to where they are. The closed-loop oracle sees this and delivers again.

### Houses

Every support surface next to a seat has a `top` close to the seat's body position, and an approach pose
1.3 m or more away from it (the ideal-profile clearance of `validate_house`). Some places have no reachable
surface, as in real homes:

| house | person / place | reachable surface |
|---|---|---|
| senior_flat | grandma, armchair / bed | side table / nightstand (often full: 4 of 4 slots) |
| care_home_suite | resident (`prefers_handover: true`), recliner / bed | side table / nightstand; handover by house profile |
| couple_flat | partner_a, sofa / bed; partner_b reading chair | side table / nightstand; none at the reading chair |
| family_house | mom, sofa / bed / front door (walk only); dad, desk chair; child, kids bed | side table / none / none; desk; none |
| korean_apt_59 | user, sofa / desk chair; grandpa (70-79, `prefers_handover: true`), bed | coffee table / desk; none (no nightstand); handover by house profile |
| korean_apt_84 | mom, sofa; child, kids bed; grandma, bed | coffee table; none; none |
| shared_flat | roommate_a, desk chair; roommate_b, bed; roommate_c, desk | desk; none; desk |
| studio_flat | user, desk chair / bed | desk; none |

`walks_to` (house YAML) adds places a person walks to without ever starting there. In family_house, mom
walks to the front door in the entrance hall, where she stands and no support surface is in reach.
Start arrangements (`from_house(house, seed_state)`) are byte-identical to round 1, because the new places
and fields do not touch the arrangement random stream.

## What a planner observes, and how the mode is chosen

`reach.person_view(world, pid)` gives what a robot's camera and house map give, and nothing else: posture,
place, room, whether the person is walking, the house profile's `prefers_handover`, and the furniture within
2 m (place, type, height, distance, free slots). It never gives a task's `mode` or a reach verdict.

Two functions, one for the task label and one for the robot's own choice:

`reach.need(world, pid, text, lang)` is what the request and the scene **require** (the bench's label):

1. the words ask for the hand (`reach.wording_wants_hand`): `hand` (`explicit`). EN counts only request forms:
   the verb (`hand me`, `hand it to`, `hand the book to grandpa`, `hand it over`, `handed to me`) or
   `in(to) my / his / her hand(s)`. The noun after a possessive or an article never counts: `My hands are full
   with the cooking`, `I just washed my hands`, `my hand hurts`; nor `hand cream`, `hand towel`, `by hand`.
   KO: `건네-`, `손에`, `손으로` (`손이 없어요`, `손을 씻었어요` are the noun and do not count);
2. the person's house profile says `prefers_handover`: `hand` (`user_needs`);
3. no support surface is within reach at all, by geometry only (a bed without a nightstand, a hallway, a seat
   with no table): `hand` (`no_surface`);
4. otherwise `reach`. A reachable surface that is full right now (a nightstand holding glasses, a phone, a
   wallet and a book) does **not** make a hand task: a real nightstand with small things on it still takes a
   cup, and making room or handing over is the robot's problem.

`reach.choose_mode(world, pid, text, lang)` is what a robot that sees the scene **does** (the oracle's choice):
the mode `need` gives, and for `reach` the nearest reachable support surface with a free slot. When every
reachable surface is full it hands over (`ModeChoice("hand", "surface_full", None)`); a handover always
satisfies `reach`. `surface_full` is a planner choice, never a task label.

The bench labels its delivery atoms with `need` at the task's start state. The oracle calls `choose_mode` with
what it observes and never reads the label (see [oracle.md](oracle.md)), so a label that only hidden
information could produce cannot happen.

Success alone does not reward choosing `reach`: a planner that always hands over also succeeds on every
`reach` task (a handover satisfies `reach`). The bench therefore reports how often a `reach` task was
handed over, and the time it cost (homeloop_bench docs/metrics.md, "Delivery mode").

## Evidence for the default

- In a Stretch user study, every participant who was busy preferred the object put on their table to a
  handover, and 77 % did when they were not busy (Phan & Cosgun 2025, Table 3,
  https://pmc.ncbi.nlm.nih.gov/articles/PMC11991642/).
- RoboCup@Home 2018 Restaurant: "The robot must place the order on the table. If the robot is not able to do
  this, the robot is allowed to hand over the order" (rulebook Sec. 6.4,
  https://athome.robocup.org/wp-content/uploads/2018/10/2018_rulebook.pdf).
- Reach geometry cross-check: mean arm length 719 mm, with the maximum reach envelope modelled as an arc about
  the shoulder (https://arxiv.org/abs/1607.04653 Table 1, Sec. 4.2). The seated reach source was opened at
  https://www.jstage.jst.go.jp/article/jpts/36/11/36_2024-013/_article/-char/en.
- Short utterances have a higher WER (https://arxiv.org/abs/2305.16065 Sec. 4.3); see the near-field ASR
  section of [calibration.md](calibration.md) and [user_model.md](user_model.md).

## API used by the bench

```python
from homeloop_robot import reach, oracle, goals
reach.delivered(world, obj, person, mode) -> bool
reach.reachable(obj, person, world) -> bool
reach.person_pose(world, pid, pos=None, moving=None) -> reach.PersonPose   # .posture, .place, .room, .moving
reach.person_view(world, pid) -> dict                    # observation: posture + nearby furniture, no label
reach.choose_mode(world, pid, text="", lang="en") -> reach.ModeChoice   # .mode, .reason, .surface
reach.wording_wants_hand(text, lang) -> bool
reach.reachable_surfaces(world, pid, free_only=False) -> list[str]
oracle.delivery_modes(world, goal, *, text="", lang="en", people_pos=None) -> {(obj, person): mode}
oracle.solve(world, goal, *, lang, people_pos=None, text=None, modes=None)
Robot.sync_people()                                      # before judging, if time passed without a call
```
