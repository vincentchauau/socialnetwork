"""Match statistics from the rallies of a match (pure functions, no database)."""

from collections.abc import Sequence
from typing import Protocol


class Played(Protocol):
    start_ms: int
    end_ms: int
    hits: int
    winner: str


def score(rallies: Sequence[Played]) -> dict[str, int]:
    """Points won by each side: every rally is one point."""
    totals = {"A": 0, "B": 0}
    for rally in rallies:
        totals[rally.winner] += 1
    return totals


def summary(rallies: Sequence[Played]) -> dict[str, int | float | dict[str, int]]:
    """Counts and averages of a match; all zero when it has no rallies."""
    count = len(rallies)
    if count == 0:
        return {"rallies": 0, "score": {"A": 0, "B": 0}, "avg_hits": 0.0, "max_hits": 0,
                "avg_duration_ms": 0.0, "longest_rally_ms": 0}
    durations = [rally.end_ms - rally.start_ms for rally in rallies]
    hits = [rally.hits for rally in rallies]
    return {
        "rallies": count,
        "score": score(rallies),
        "avg_hits": round(sum(hits) / count, 2),
        "max_hits": max(hits),
        "avg_duration_ms": round(sum(durations) / count, 1),
        "longest_rally_ms": max(durations),
    }
