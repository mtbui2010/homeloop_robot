"""homeloop_robot: a stochastic mock household robot (docs/architecture.md).

Public API (DESIGN 13.1). Names are resolved lazily, so ``import homeloop_robot`` is cheap and a
module of the package can import another without cycles.
"""

from __future__ import annotations

import importlib

__version__ = "0.1.0"

_EXPORTS = {
    "FailureCode": "types", "SkillResult": "types", "Call": "types",
    "Streams": "rng", "derive_seed": "rng", "rng_for": "rng", "r6": "rng",
    "SimClock": "clock",
    "World": "world", "from_house": "world",
    "list_houses": "houses", "load_house": "houses",
    "CLASSES": "catalog", "MESSAGES": "catalog",
    "load_profile": "profiles", "Profile": "profiles",
    "Robot": "skills", "SKILL_SPECS": "skills",
    "make_episode": "episode", "Episode": "episode",
}
_MODULES = ("goals", "oracle")

__all__ = sorted(list(_EXPORTS) + list(_MODULES))


def __getattr__(name):
    if name in _EXPORTS:
        mod = importlib.import_module(f"{__name__}.{_EXPORTS[name]}")
        val = getattr(mod, name)
        globals()[name] = val
        return val
    if name in _MODULES:
        mod = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = mod
        return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
