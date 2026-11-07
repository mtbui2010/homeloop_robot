"""A clarify read-back (structured confirm with the plan in the goal slot) that names the intended candidate is
right only when it also covers every atom of the request: another destination or an extra Say gets 'no, ...'."""
import pytest

from test_dialog_structured import GLASS_SPEC, _ask

GOAL = {"all": [{"pred": "delivered", "args": ["mug_2", "user"], "mode": "reach", "mode_reason": None},
                {"pred": "on", "args": ["remote_1", "tv_stand@living"]}]}
REQ = {"en": "Could you bring me a mug and put the remote on the TV stand?",
       "ko": "머그컵 좀 갖다 주고 리모컨은 티비장 위에 놔 줄래요?"}
READBACK = {
    "right": {"en": "I will bring you the green mug and put the remote on the TV stand. Is that right?",
              "ko": "초록색 머그컵을 갖다 드리고 리모컨을 티비장 위에 놓을게요. 맞죠?"},
    "dest": {"en": "I will bring you the green mug and put the remote on the sofa. Is that right?",
             "ko": "초록색 머그컵을 갖다 드리고 리모컨을 소파 위에 놓을게요. 맞죠?"},
    "say": {"en": "I will bring you the green mug, put the remote on the TV stand and tell Grandpa dinner is "
                  "ready. Is that right?",
            "ko": "초록색 머그컵을 갖다 드리고 리모컨을 티비장 위에 놓고 할아버지께 저녁 준비됐다고 말할게요. 맞죠?"},
}


def _confirm(L, key):
    q = READBACK[key][L]
    return _ask(L, q, {"qtype": "confirm", "goal": q}, spec=GLASS_SPEC, goal=GOAL, req=REQ)


@pytest.mark.parametrize("L", ["en", "ko"])
def test_right_readback_with_the_intended_candidate_is_yes(L):
    r, log = _confirm(L, "right")
    assert r.kind == "yes", (r.text, log)


@pytest.mark.parametrize("L", ["en", "ko"])
@pytest.mark.parametrize("key", ["dest", "say"])
def test_readback_naming_the_candidate_but_wrong_elsewhere_is_no(L, key):
    r, log = _confirm(L, key)
    assert r.kind == "no", (r.text, log)
    assert r.text.startswith({"en": "No", "ko": "아니"}[L]), r.text
