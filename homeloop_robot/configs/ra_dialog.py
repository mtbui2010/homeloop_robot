"""The structured form of robot_agent's (SAGE-v2 AssistLoop) questions (R2-7a, docs/user_model.md).

robot_agent writes every question of the AssistLoop in English from fixed templates and translates it into the
user's language just before its Ask skill runs (``AssistLoop._ask_io`` -> ``_in_lang``). The bench adapter
(homeloop_bench ``planners/robot_agent_adapter.py``) wraps ``_ask_io`` on the loop instance, so it sees the
English question before translation, and :func:`derive` maps it onto a template id, a qtype of
``homeloop_robot.intent.QTYPES`` and its slots. robot_agent itself is not changed.

The templates below are copied from robot_agent (file and function named per entry); a test
(tests/test_dialog_structured_ra.py) builds the questions with robot_agent's own functions and checks that
each one is derived. A question with no template (the understanding LLM's own ``question``, or a template this
list does not know) gets no meaning: the simulated user reads its text (rules, then the LLM classifier).
"""
from __future__ import annotations

import re

# a slot never runs across a question mark: SAGE joins questions, and an empty slot ("Where should I put the ?
# Where should I put the green mug?") must not swallow the next question (pilot round 1, hl-dev-000010 KO)
_S = r"[^?]+?"
_OPT = r"(?P<opts>" + _S + ")"


def _opts(s: str) -> list:
    return [x.strip() for x in re.split(r"\s+or\s+", str(s or "")) if x.strip()]


# (template id, regex over the whole English segment, qtype, slot builder)
TEMPLATES = [
    # assist_loop._read_back: "I am not sure I understood (...). " + summary(goals) + " Is that right?"
    ("read_back", r"(?:I am not sure I understood \(.*?\)\. )?(?P<goal>I will .+?) Is that right\?",
     "confirm", lambda m: {"goal": m["goal"]}),
    # assist_loop goal_change: a new request from someone else during a run
    ("new_task_first", r"Someone asked me to .+?\. Should I do that first\? If not, I will do it after the "
                       r"current task\.", "free", lambda m: {}),
    # assist_loop._ground_goals: a "to me" goal without the user's place
    ("where_user", r"Where are you\? Which place should I bring it to\?", "where_are_you", lambda m: {}),
    # goals.conflicts: two destinations for one object
    ("two_destinations", r"Where should the (?P<obj>[^?]+?) go in the end: " + _OPT + r"\? It cannot be in two "
                         r"places\.", "which_place", lambda m: {"obj": m["obj"], "options": _opts(m["opts"])}),
    # assist_loop._ground_template
    ("which_place", r"Which place do you mean: " + _OPT + r"\?", "which_place",
     lambda m: {"options": _opts(m["opts"])}),
    # assist_loop._ground_goals / understand.issue_question
    ("which_x", r"Which (?P<what>[^?:]+?) do you mean: " + _OPT + r"\?", "which_place",
     lambda m: {"options": _opts(m["opts"])}),
    # assist_loop._ground_container
    ("which_drawer", r"Which drawer should I (?P<verb>open|close)\?", "which_place", lambda m: {"verb": m["verb"]}),
    # assist_loop._ground_template
    ("what_to_say", r"What should I say\?", "what_to_say", lambda m: {}),
    ("where_go", r"Where should I go\?", "which_place", lambda m: {}),
    ("where_take", r"Where should I take it\?", "which_place", lambda m: {}),
    # assist_loop._ground_goals / understand.issue_question ("unsaid")
    ("where_put", r"Where should I put the (?P<obj>[^?]+?)\?", "which_place", lambda m: {"obj": m["obj"]}),
    # understand.issue_question ("place"): an open question about a place the person named
    # (an open "what should I do?": the person says the task again, homeloop_robot.intent convention 3)
    ("mentioned_place", r"You mentioned the (?P<what>[^?]+?)\. What should I do there\?", "repeat",
     lambda m: {"about": "request"}),
    # understand.issue_question ("object")
    ("do_with", r"What should I do with the (?P<obj>[^?]+?)\?", "which_place", lambda m: {"obj": m["obj"]}),
    # assist_loop._understand_round / _read_back: the task itself, again
    ("what_to_do", r"(?:Sorry\. )?What should I do(?: exactly)?\?", "repeat", lambda m: {"about": "request"}),
    ("other_words", r"Sorry, I did not understand\. Could you say the task in other words\?", "repeat",
     lambda m: {"about": "request"}),
    # understand.issue_question ("verb"): the request says open / close (understand._VERB: "open", "close", which
    # also reads "shut") and no goal does it: which container or door to open / close, a place, with the verb kept;
    # only these verbs, so the LLM's own "What should I tell dad?" gets no meaning
    ("what_verb", r"What should I (?P<verb>open|close|shut)\?", "which_place", lambda m: {"verb": m["verb"]}),
    # understand.misheard_question with no earlier question
    ("say_again", r"(?:Sorry, I may have misheard you\. )?Could you say that again\?", "repeat",
     lambda m: {"about": "request"}),
    # robot.CORE_TEXT yes_or_no (interact.dialog.ask_yes_no re-ask)
    ("yes_or_no", r"Sorry, I didn't catch that\. Please answer yes or no\.", "repeat",
     lambda m: {"about": "answer"}),
    # assist_loop search help
    ("not_found", r"I couldn't find the (?P<obj>[^?]+?)\. Where is it\?", "where_is", lambda m: {"obj": m["obj"]}),
    # assist_loop pick help
    ("pick_help", r"(?:The (?P<obj>[^?]+?) is too far for my arm|I can't pick up the (?P<obj2>[^?]+?))\. Could you "
                  r"move it closer to the edge, then say yes\?", "help", lambda m: {}),
    # assist_loop move help
    ("move_help", r"I can't get to the (?P<place>[^?]+?)\. Is something in the way\? Please clear the way and say "
                  r"yes\.", "help", lambda m: {}),
]
_RX = [(tid, re.compile(rx), qt, fn) for tid, rx, qt, fn in TEMPLATES]
MISHEARD = "Sorry, I may have misheard you. "
SILENCE = "Sorry, I didn't hear you. "          # interact.dialog.ask_heard: the question again after silence
_SENT = re.compile(r"(?<=[?.!])\s+")


def _match(seg: str):
    best = None
    for tid, rx, qt, fn in _RX:
        m = rx.match(seg)
        if m and (best is None or m.end() > best[0].end()):
            best = (m, tid, qt, fn)
    return best


def derive(question: str) -> dict | None:
    """``{"qtype", slots..., "template": [ids]}`` for an English AssistLoop question, or None (no template).

    A question may join several templates ("Which shelf do you mean: A or B? Where should I put the cup?") or a
    template and the LLM's own words: the templates are matched left to right (the longest at each point; text
    no template matches is skipped one sentence at a time). The first template gives the qtype; slots of later
    templates of the same qtype are added."""
    q = re.sub(r"\s+", " ", str(question or "")).strip()
    pre = []
    if q.startswith(SILENCE) and len(q) > len(SILENCE):
        q, pre = q[len(SILENCE):], ["silence_retry"]
    if q.startswith(MISHEARD) and not q.startswith(MISHEARD + "Could you say that again?"):
        q = q[len(MISHEARD):]                  # understand.misheard_question: the earlier question again
    found = []
    i = 0
    while i < len(q):
        rest = q[i:]
        hit = _match(rest)
        end_ok = hit is not None and (hit[0].end() == len(rest) or rest[hit[0].end()] == " ")
        if end_ok:
            m, tid, qt, fn = hit
            found.append((tid, qt, fn(m.groupdict())))
            i += m.end()
        else:
            parts = _SENT.split(rest, maxsplit=1)
            if len(parts) < 2:
                break
            i += len(rest) - len(parts[1])
        while i < len(q) and q[i] == " ":
            i += 1
    if not found:
        return None
    tid0, qt0, slots0 = found[0]
    out = {"qtype": qt0, **{k: v for k, v in slots0.items() if v}}
    for _tid, qt, slots in found[1:]:
        if qt == qt0:
            for k, v in slots.items():
                if v and k not in out:
                    out[k] = v
    out["template"] = pre + [t for t, _q, _s in found]
    return out
