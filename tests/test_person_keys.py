"""Person ENV keys are what the user hears (pilot round 1, hl-dev-000010 / 000013): robot_agent reads a plan back
with the ENV key itself ("I will put the mug on the {key}.", AssistLoop.summary), so no person key is a raw id
('person_user', 'partner_b'). The speaker's entry is SPEAKER_KEY ("spot within your reach") (said to them), anyone else's is their name."""
import re

import pytest

from helpers import HAS_RA

from homeloop_robot.configs.tasks import (RESERVED_USER_WORDS, SPEAKER_KEY, _words, env_for, person_key,
                                          person_keys)
from homeloop_robot.episode import make_episode
from homeloop_robot.houses import list_houses
from homeloop_robot.world import from_house


@pytest.mark.parametrize("house", list_houses())
def test_person_keys_are_names_not_ids(house):
    w = make_episode(house, 0, "ideal", 0).world
    env = env_for(w)
    keys = person_keys(w)
    uid = w.user_id()
    assert keys[uid] == SPEAKER_KEY
    for pid, k in keys.items():
        assert env[k]["person"] == pid and person_key(w, pid) == k
        assert "_" not in k and "@" not in k, (house, pid, k)            # no raw id
        assert _words(k) not in RESERVED_USER_WORDS
        if pid != uid:
            name = re.sub(r"^(the|a|an|my) ", "", w.people[pid].name["en"].lower())
            assert k == name, (house, pid, k)
    assert len(set(keys.values())) == len(keys)


def test_known_keys():
    w = make_episode("couple_flat", 0, "ideal", 0).world
    assert person_keys(w) == {"partner_a": SPEAKER_KEY, "partner_b": "husband"}
    w = make_episode("korean_apt_59", 0, "ideal", 0).world
    assert person_keys(w) == {"grandpa": "grandpa", "user": SPEAKER_KEY}
    w = make_episode("shared_flat", 0, "ideal", 0).world
    assert person_keys(w)["roommate_b"] == "roommate b"


def test_speaker_key_does_not_end_in_a_request_word():
    """robot_agent takes the last word of a multi-word ENV head as a place phrase (understand._phrases), so the key's
    last word must not be a word of everyday requests: "spot near you" made every "Can you ..." a mention of the
    speaker's spot (fresh pilot round 1, hl-dev-000057 / 000016 EN; the bench's tests/test_person_key_mentions.py
    checks every dev / test instruction)."""
    last = SPEAKER_KEY.split()[-1]
    assert last not in RESERVED_USER_WORDS | {"there", "it", "your", "my", "now", "please"}, SPEAKER_KEY


@pytest.mark.skipif(not HAS_RA, reason="robot_agent not importable")
@pytest.mark.parametrize("house", list_houses())
def test_robot_agent_does_not_hear_you_as_the_speakers_spot(house):
    from robot_agent.core.planning.assist_loop import Places
    from robot_agent.core.planning.understand import place_mentions
    env = env_for(from_house(house, 0))
    for text in ("Can you put the green book on the coffee table?", "Could you tell my son it's time for bed?",
                 "Thank you, can you do that now?"):
        # a person is mentioned only by a name of theirs ("my son"), never by a stray word of the key ("you")
        stray = [m for m in place_mentions(text, Places(env)) for k in m[3] if env[k].get("person")
                 and m[2].lower() not in {k.lower()} | {a.lower() for a in env[k]["aliases"]}]
        assert not stray, (house, text, stray)
    got = place_mentions("Put it on the spot within your reach.", Places(env))
    assert any(SPEAKER_KEY in m[3] for m in got), got
