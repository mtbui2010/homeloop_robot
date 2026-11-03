"""SAGE-v2 (robot_agent AssistLoop) questions -> qtype + slots (configs/ra_dialog.derive, R2-7a).

The questions are built with robot_agent's own functions where they are plain functions (summary, issue_question,
conflicts, misheard_question, the yes_or_no text, ask_heard's re-ask), and every template's wording must still be
in robot_agent's source, so a change of a template there fails here. Skipped without robot_agent."""
import inspect
import re
from pathlib import Path

import pytest

from homeloop_robot.configs.ra_dialog import TEMPLATES, derive

ra = pytest.importorskip("robot_agent")
from robot_agent.core.planning import assist_loop as AL  # noqa: E402
from robot_agent.core.planning import goals as RG  # noqa: E402
from robot_agent.core.planning import robot as RR  # noqa: E402
from robot_agent.core.planning import understand as U  # noqa: E402
from robot_agent.core.planning.robot import CORE_TEXT  # noqa: E402
from robot_agent.interact import dialog as RD  # noqa: E402

SRC = "\n".join(Path(m.__file__).read_text(encoding="utf-8") for m in (AL, RG, U, RD, RR))

# a fixed wording of each template as it stands in robot_agent's source
ANCHORS = {
    "read_back": "Is that right?", "new_task_first": "Should I do that first? ",
    "where_user": "Where are you? Which place should I bring it to?", "two_destinations": "It cannot be in two places.",
    "which_place": "Which place do you mean: ", "which_x": "do you mean: ", "which_drawer": "Which drawer should I ",
    "what_to_say": "What should I say?", "where_go": "Where should I go?", "where_take": "Where should I take it?",
    "where_put": "Where should I put the ", "mentioned_place": "What should I do there?",
    "do_with": "What should I do with the ", "what_to_do": "What should I do exactly?",
    "other_words": "Could you say the task in other words?", "what_verb": "What should I ",
    "say_again": "Could you say that again?", "yes_or_no": "Please answer yes or no.",
    "not_found": "Where is it?", "pick_help": "Could you move it closer to the edge, then say yes?",
    "move_help": "Please clear the way and say yes.",
}


def test_every_template_wording_is_in_robot_agent():
    assert set(ANCHORS) == {t[0] for t in TEMPLATES}
    for tid, anchor in ANCHORS.items():
        assert anchor in SRC, f"{tid}: {anchor!r} no longer in robot_agent"


def test_read_back_from_summary():
    goals = [{"type": "on", "object": "red mug", "to": "counter@kitchen", "from": ""},
             {"type": "in", "object": "milk", "to": "fridge@kitchen"}]
    s = AL.AssistLoop.summary(goals)
    for q in (f"{s} Is that right?", f"I am not sure I understood (the sink you mentioned is not in my plan). {s} "
                                     f"Is that right?", f"Sorry, I didn't hear you. {s} Is that right?"):
        m = derive(q)
        assert m["qtype"] == "confirm" and m["goal"] == s


def test_issue_questions():
    places = None
    q = U.issue_question([{"kind": "unsaid", "object": "cup"}], places)
    assert derive(q) == {"qtype": "which_place", "obj": "cup", "template": ["where_put"]}
    q = U.issue_question([{"kind": "place", "what": "shelf", "keys": ["shelf@kitchen", "shelf@living"]},
                          {"kind": "unsaid", "object": "cup"}], places)
    m = derive(q)
    assert m["qtype"] == "which_place" and m["options"] == ["shelf in the kitchen", "shelf in the living"]
    assert m["template"] == ["which_x"]
    q = U.issue_question([{"kind": "object", "what": "towel"}], places)
    assert derive(q)["qtype"] == "which_place" and derive(q)["obj"] == "towel"
    # the verb issue: robot_agent's own verbs (understand._VERB), a question about which container / door
    assert set(U._VERB) == {"open", "close"}
    for verb in U._VERB:
        q = U.issue_question([{"kind": "verb", "what": verb}], places)
        assert derive(q) == {"qtype": "which_place", "verb": verb, "template": ["what_verb"]}
    q = U.issue_question([{"kind": "place", "what": "sofa"}], places)
    assert derive(q)["qtype"] == "repeat"         # an open "what should I do there?": the task again


def test_conflict_and_misheard_and_yes_or_no():
    _g, q = RG.conflicts([{"type": "on", "object": "mug", "to": "counter@kitchen"},
                          {"type": "on", "object": "mug", "to": "sink@kitchen"}])
    m = derive(q)
    assert m["qtype"] == "which_place" and m["obj"] == "mug" and len(m["options"]) == 2
    _d, q = U.misheard_question([("robot", "Where should I put the cup?"), ("user", "uh")])
    assert derive(q)["qtype"] == "which_place" and derive(q)["obj"] == "cup"
    _d, q = U.misheard_question([])
    assert derive(q) == {"qtype": "repeat", "about": "request", "template": ["say_again"]}
    assert derive(CORE_TEXT["yes_or_no"]) == {"qtype": "repeat", "about": "answer", "template": ["yes_or_no"]}
    again = inspect.signature(RD.ask_heard).parameters["again"].default
    assert derive(again.format(q="Where are you? Which place should I bring it to?"))["qtype"] == "where_are_you"


@pytest.mark.parametrize("q,qt,slots", [
    ("Which place do you mean: shelf in the kitchen or shelf in the living?", "which_place",
     {"options": ["shelf in the kitchen", "shelf in the living"]}),
    ("Which drawer should I open?", "which_place", {}),
    ("What should I say?", "what_to_say", {}),
    ("Where should I go?", "which_place", {}),
    ("Where should I take it?", "which_place", {}),
    ("Where are you? Which place should I bring it to?", "where_are_you", {}),
    ("What should I do exactly?", "repeat", {"about": "request"}),
    ("Sorry. What should I do?", "repeat", {"about": "request"}),
    ("Sorry, I did not understand. Could you say the task in other words?", "repeat", {"about": "request"}),
    ("I couldn't find the red mug. Where is it?", "where_is", {"obj": "red mug"}),
    ("The red mug is too far for my arm. Could you move it closer to the edge, then say yes?", "help", {}),
    ("I can't pick up the red mug. Could you move it closer to the edge, then say yes?", "help", {}),
    ("I can't get to the sink in the kitchen. Is something in the way? Please clear the way and say yes.", "help", {}),
    ("Someone asked me to put the cup on the sink. Should I do that first? If not, I will do it after the current "
     "task.", "free", {}),
])
def test_assist_loop_templates(q, qt, slots):
    m = derive(q)
    assert m["qtype"] == qt
    for k, v in slots.items():
        assert m[k] == v


def test_llm_own_question_has_no_meaning():
    assert derive("Do you want the mug washed first?") is None
    # "What should I <verb>?" is a template only for robot_agent's open / close verb issue
    for q in ("What should I tell dad?", "What should I do first?", "What should I bring?"):
        assert derive(q) is None, q
    assert derive("") is None
    # the LLM's words first, then a template: the template gives the meaning
    m = derive("Hmm, two shelves. Which place do you mean: shelf in the kitchen or shelf in the living?")
    assert m["qtype"] == "which_place"


def test_templates_compile_and_anchor_regex_sanity():
    for tid, rx, qt, _fn in TEMPLATES:
        re.compile(rx)
        assert qt in ("which_object", "which_place", "confirm", "where_are_you", "where_is", "repeat",
                      "did_you_mean", "what_to_say", "help", "free"), tid
