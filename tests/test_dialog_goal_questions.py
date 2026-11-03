"""Questions about the user's own request that a real person answers (found in the R2-5 rerun, docs/user_model.md):
"Where should they go?" / "어디에 두면 될까요?" when several things were asked for, and "Which place in the bedroom
should I wait at?" when the request named only the room."""
import pytest

from homeloop_robot.dialog import GoalView, compose
from homeloop_robot.world import from_house

TWO = {"all": [{"pred": "in", "args": ["apple_1", "fridge@kitchen"]},
               {"pred": "delivered", "args": ["mug_1", "user"], "mode": "reach", "mode_reason": None}]}


def _ans(q, L, wants, house="korean_apt_59", user="user"):
    w = from_house(house, 0)
    gv = GoalView(w, wants, user, lambda pid: None)
    return compose(q, L, {"persona": "adult"}, w, knows_location=True, user_place=(None, False), goal=gv,
                   request="(request)", last_answer=None)


@pytest.mark.parametrize("L,q", [
    ("en", "What objects need to be put away and where should they go?"),
    ("en", "Where should I put them?"),
    ("en", "Where should I take the things?"),
    ("ko", "어디에 두면 될까요?"),
    ("ko", "여기 있어요? 어디에 가져다줘야 할까요?"),
])
def test_destination_of_several_things_lists_each(L, q):
    c = _ans(q, L, TWO)
    assert c.rule == "goal_destination" and c.kind == "correct" and c.informative
    if L == "en":
        assert "fridge" in c.text and "to me" in c.text
    else:
        assert "냉장고" in c.text and "저한테" in c.text


def test_destination_without_a_pronoun_or_object_is_still_not_answered():
    # robot_agent's empty-slot question ("Where should I put the ?") names nothing the user can answer about
    assert _ans("Where should I put the ?", "en", TWO).rule != "goal_destination"


def test_one_destination_unchanged():
    one = {"all": [TWO["all"][0]]}
    assert _ans("Where should I put it?", "en", one).text == "In the fridge, please."


ROOM = {"all": [{"any": [{"pred": "robot_at", "args": [p]} for p in
                         ("bed@bedroom", "dresser@bedroom", "floor@bedroom", "nightstand@bedroom",
                          "wardrobe@bedroom")]}]}


@pytest.mark.parametrize("L,q,text", [
    ("en", "Which place in the bedroom should I wait at?", "Anywhere in the bedroom is fine."),
    ("en", "Which specific place in the bedroom should I wait at?", "Anywhere in the bedroom is fine."),
    ("ko", "침실 어디에서 기다리면 될까요?", "침실 안이면 아무 데나 괜찮아요."),
])
def test_room_only_request_any_spot_in_it(L, q, text):
    c = _ans(q, L, ROOM, house="senior_flat", user="grandma")
    assert (c.rule, c.kind, c.text) == ("goal_room", "correct", text)


def test_room_rule_needs_the_room_and_a_place_question():
    assert _ans("Which place in the kitchen should I wait at?", "en", ROOM, house="senior_flat",
                user="grandma").rule != "goal_room"
    assert _ans("Should I wait in the bedroom?", "en", ROOM, house="senior_flat", user="grandma").rule != "goal_room"
    # a list of places is still answered with the first one asked for (rule 3)
    c = _ans("Which place do you mean: bed in the bedroom or dresser in the bedroom?", "en", ROOM,
             house="senior_flat", user="grandma")
    assert c.rule == "goal_place"
