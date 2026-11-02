"""Seeds: every random draw of the mock robot goes through here (docs/architecture.md, Determinism).

``derive_seed`` hashes its parts with SHA-256, so a draw depends only on the names it is keyed by,
never on call order across unrelated streams, Python's salted ``hash()`` or the wall clock.
"""

from __future__ import annotations

import hashlib
import random


def derive_seed(*parts) -> int:
    """A 64-bit seed from any parts (joined with '|')."""
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).digest()[:8], "big")


def rng_for(*parts) -> random.Random:
    """A fresh ``random.Random`` seeded from ``parts``."""
    return random.Random(derive_seed(*parts))


class Streams:
    """Named random streams of one episode.

    ``stream(name)`` gives one long-lived Random per name (created on first use);
    ``rng_for(*parts)`` gives a fresh Random keyed by (seed, key, *parts): the same call in two
    episodes with the same key draws the same numbers (common random numbers)."""

    def __init__(self, seed: int, key: str = ""):
        self.seed = int(seed)
        self.key = str(key)
        self._streams: dict[str, random.Random] = {}

    def stream(self, name: str) -> random.Random:
        r = self._streams.get(name)
        if r is None:
            r = self._streams[name] = random.Random(derive_seed(self.seed, self.key, "stream", name))
        return r

    def rng_for(self, *parts) -> random.Random:
        return random.Random(derive_seed(self.seed, self.key, *parts))


def r6(x: float) -> float:
    """round(x, 6), with -0.0 -> 0.0 (stable JSON)."""
    y = round(float(x), 6)
    return 0.0 if y == 0 else y
