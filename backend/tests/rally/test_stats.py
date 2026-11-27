from types import SimpleNamespace

from api.rally import stats


def played(start: int, end: int, hits: int, winner: str) -> SimpleNamespace:
    return SimpleNamespace(start_ms=start, end_ms=end, hits=hits, winner=winner)


def test_summary_is_zero_without_rallies() -> None:
    result = stats.summary([])

    assert result["rallies"] == 0
    assert result["score"] == {"A": 0, "B": 0}
    assert result["avg_hits"] == 0.0


def test_summary_counts_score_hits_and_durations() -> None:
    rallies = [played(0, 800, 2, "A"), played(1000, 4000, 6, "B"), played(5000, 5600, 4, "B")]

    result = stats.summary(rallies)

    assert result["rallies"] == 3
    assert result["score"] == {"A": 1, "B": 2}
    assert result["avg_hits"] == 4.0
    assert result["max_hits"] == 6
    assert result["longest_rally_ms"] == 3000
