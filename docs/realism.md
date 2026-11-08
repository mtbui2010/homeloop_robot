# Realism

Requirement: every object, placement, house, failure and outcome of the mock robot is something that
happens in real homes; synthetic variety must not create impossible or unheard-of cases. Two commands
check this (both are in the acceptance checks):

```
python -m homeloop_robot.realism --strict                 # catalog + houses (R-a, R-b, R-c, R-d, R-h)
python -m homeloop_robot.profiles consistency --strict    # outcome rates + physical possibility
```

`homeloop_bench`'s `data realism` command reuses `homeloop_robot.realism` (`placement_ok` for goal
destinations, `report` for the robot-side rules) and adds its task rules (R-e, R-f, R-g).

## Where objects and receptacles come from

| source | what was taken | URL |
|---|---|---|
| AI2-THOR object types (the object and receptacle types of ALFRED) | object types and their "Default Compatible Receptacles"; receptacle categories (CounterTop, SinkBasin, Fridge, Cabinet, Drawer, Shelf, DiningTable, CoffeeTable, SideTable, Desk, TVStand, Sofa, ArmChair, Bed, Box, Microwave, StoveBurner, Sink, Chair) | https://ai2thor.allenai.org/ithor/documentation/objects/object-types |
| ALFRED (Shridhar et al., 2020) | the benchmark that uses these object / receptacle types | https://arxiv.org/abs/1912.01734 |
| YCB object set, Table II (Calli et al. 2015) | object identities and masses: mug 118 g, plate 279 g, bowl 147 g, fork 34 g, spoon 30 g, knife 31 g, wine glass 133 g, scissors 82 g, keys 6 g, apple 68 g, orange 47 g, banana 66 g, tomato soup can 349 g, cereal box 510 g | https://arxiv.org/abs/1502.03143 |
| OK-Robot payload limit (Sec. III-D) | 1 kg: heavier objects are not graspable | https://arxiv.org/abs/2401.12202 |
| BEHAVIOR-1K knowledge base (Li et al.), synset `pill_bottle.n.01` ("a small bottle for holding pills", child of `bottle.n.01`) | the common English name "pill bottle", declared as an alias of `medicine_bottle` (the camera's detector reads it; the pill organizer keeps its own name "pill box") | https://behavior.stanford.edu/knowledgebase/synsets/pill_bottle.n.01.html |
| Korean colloquial "폰" (short for 휴대폰, "mobile phone") | declared as a Korean alias of `phone`; no published source, `assumed`: a household member says it, the detector reads it | - |

Each catalog class (`homeloop_robot/catalog.py`, `REALISM`) has `category`, `provenance` (set, item,
URL; or a note that no published set has the item, e.g. a kimchi container or a pill organizer),
`mass_kg` (YCB where the class is a YCB object, else a nominal value marked assumed), `size_class`
(xs / s / m / l / xl), `graspable`, `liquid` (every liquid is packaged: bottle, carton, jug), `fragile`,
`sharp`, `food`, `hot`, and `typical_receptacles`: each entry is either in the AI2-THOR list of the class's
AI2-THOR type (narrowed to the plausible subset: a mug is not kept in a microwave even though AI2-THOR
allows it) or an assumption with its reason (e.g. keys in the entryway shoe cabinet of Korean homes).
Categories AI2-THOR does not have (Wardrobe, ShoeCabinet, DryingRack) are marked assumed with a note.
Each receptacle category has `room_types` and `capacity_size_class`.

## Robot-side rules (`homeloop_robot/realism.py`)

| rule | check |
|---|---|
| R-a | every class has the provenance and attribute fields above; every typical receptacle is a known category with a source or an assumed reason; every receptacle category has room types and a capacity size |
| R-b | every object's initial place and every alternative place in every house is one of its class's typical receptacles (`placement_ok`) |
| R-c | an object never goes into a receptacle smaller than it (size class <= capacity size class); no unpackaged liquid |
| R-d | `graspable` agrees with the mass, the grasp class and the payload limit; the robot's `pick` refuses exactly the non-graspable classes |
| R-h | every room has a type; kitchens have a counter, a kitchen sink and a fridge, bathrooms a sink (or toilet), bedrooms a bed; every receptacle category is in a room type it belongs to; every place pair is 0.5-20 m apart by path; 15-80 objects per house and at most 12 per receptacle (assumed ranges) |

Houses also pass `validate_house` ([world.md](world.md)): connectivity, capacities, and the
ideal-safety clearances.

## Outcome consistency (`homeloop_robot/consistency.py`)

1. Rates: for every failure / recovery parameter of the `real` profile (39 checks), 20,000 seeded calls
   in the parameter's reference context (e.g. `move.p_fail.high`: moves to a high-clutter place;
   `pick.p_retry_success`: the second pick after a failed one; `find.p_wrong_instance.many`: a find with a
   confusable object at a high-clutter place). The empirical rate must pass an exact two-sided binomial
   test at the 0.1 % level against the profile's rate (it lies in the 99.9 % binomial interval). Rates
   that depend on context are measured conditionally (e.g. the failure split given a failure, the slip
   rate given a reported success); the report lists the context of each.
2. Physical possibility, on random traces (oracle steps + random calls; every house; ideal, real and
   stress): no `dropped` without holding; no `grasp_failed` outside pick / handover (a place with an
   empty hand is `absent`, a handle the robot cannot get is `unreachable`); no success effect after a
   failure (only a drop moves the held object to the floor); no `absent` for an object truly visible
   at the robot's place in `ideal` (pick detects a visible object itself); durations of successful calls
   inside each skill's cited range.
3. The simulated user's and the ASR model's own consistency hooks (`user.consistency`,
   `asr.consistency`), when the user part is installed.

## Activity and hazard provenance

Task activities (ALFRED task types, SayCan, AmbiK, KnowNo, RoboCup@Home GPSR) and hazard categories
(SafeAgentBench) are cited by the bench (its docs/realism.md); semantic hazard rules of the robot are in
the robot-human-safety part (hazards).
