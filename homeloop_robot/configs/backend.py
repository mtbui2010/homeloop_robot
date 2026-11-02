"""The robot the robot_agent skill functions drive: ``get_backend()`` / ``set_backend(robot)``.

The bench sets an episode-bound proxy (its ``call`` goes through the episode's budgets and call log).
Without one, a default robot is built on ``DEFAULT_HOUSE`` in the ``ideal`` profile. No robot_agent
import here.
"""

from __future__ import annotations

DEFAULT_HOUSE = "senior_flat"

_backend = None


def set_backend(robot) -> None:
    """Install the object the skills call: anything with ``call(skill, **args) -> SkillResult``
    (and optionally ``world``, ``observe()``, ``health()``, ``believed``)."""
    global _backend
    _backend = robot


def get_backend():
    global _backend
    if _backend is None:
        from ..episode import make_episode
        _backend = make_episode(DEFAULT_HOUSE, 0, "ideal", 0, key="configs-default").robot
    return _backend


def reset_backend() -> None:
    global _backend
    _backend = None
