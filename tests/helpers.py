"""Shared test helpers (not a test module)."""

import importlib.util

from homeloop_robot.episode import make_episode
from homeloop_robot.profiles import Profile, load_profile

HAS_RA = importlib.util.find_spec("robot_agent") is not None


def episode(house="senior_flat", profile="ideal", seed=0, seed_state=0, key="t", **kw):
    return make_episode(house, seed_state, profile, seed, key=key, user_impl="null", safety_impl="null", **kw)


def patched(base: str = "ideal", **values) -> Profile:
    """A copy of profile ``base`` with some values replaced (keys with dots: pass as a dict)."""
    p = load_profile(base)
    params = {k: dict(v) for k, v in p.params.items()}
    for k, v in values.items():
        params[k.replace("__", ".")]["value"] = v
    return Profile(f"{base}-patched", params)
