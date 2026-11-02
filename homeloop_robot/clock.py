"""The simulated clock: skills advance it by their simulated duration (no wall clock anywhere)."""

from __future__ import annotations


class SimClock:
    def __init__(self, t: float = 0.0):
        self.t = float(t)

    def advance(self, dt: float) -> float:
        """Move the clock forward by ``dt`` >= 0 seconds and return the new time."""
        dt = float(dt)
        if dt < 0:
            raise ValueError(f"SimClock.advance: negative dt {dt}")
        self.t += dt
        return self.t

    def __repr__(self) -> str:
        return f"SimClock(t={self.t:.3f})"
