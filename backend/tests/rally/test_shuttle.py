import numpy as np
import pytest

from api.rally.shuttle import Track, find_candidates, shuttle_at, step


def blank() -> np.ndarray:
    return np.zeros((480, 640), dtype=np.uint8)


def spot(frame: np.ndarray, x: int, y: int) -> np.ndarray:
    frame[y - 1:y + 2, x - 1:x + 2] = 255
    return frame


def test_a_moving_bright_spot_is_a_candidate() -> None:
    previous = blank()
    current = spot(blank(), 320, 240)

    found = find_candidates(previous, current)

    assert len(found) == 1
    assert found[0][0] == pytest.approx(320 / 640, abs=0.01)
    assert found[0][1] == pytest.approx(240 / 480, abs=0.01)


def test_a_static_bright_spot_is_not_a_candidate() -> None:
    still = spot(blank(), 100, 100)

    assert find_candidates(still, still.copy()) == []


def test_the_shuttle_is_the_moving_spot_among_distractions() -> None:
    tracks: tuple[Track, ...] = ()
    for frame_index in range(10):
        shuttle = (100 + 12 * frame_index, 60 + 3 * frame_index)  # moves smoothly across the frame
        distraction = (500, 400 + (frame_index % 2) * 20)  # jumps about, as a player would
        candidates = [(x / 640, y / 480) for x, y in (shuttle, distraction)]
        tracks = step(tracks, candidates, frame_index)

    position = shuttle_at(tracks, 9)

    assert position is not None
    assert position[0] == pytest.approx((100 + 12 * 9) / 640, abs=0.005)
    assert position[1] == pytest.approx((60 + 3 * 9) / 480, abs=0.005)


def test_no_track_gives_no_shuttle() -> None:
    assert shuttle_at((), 5) is None


def test_a_track_seen_only_once_is_not_the_shuttle() -> None:
    tracks = step((), [(0.5, 0.5)], 0)

    assert shuttle_at(tracks, 0) is None


def test_a_track_not_extended_for_too_long_is_forgotten() -> None:
    tracks = step((), [(0.2, 0.2)], 0)
    for frame_index in range(1, 30):
        tracks = step(tracks, [], frame_index)

    assert tracks == ()


def test_a_cluster_of_spots_is_dropped_but_a_lone_spot_is_kept() -> None:
    from api.rally.shuttle import drop_clusters

    cluster = [(0.50, 0.50), (0.51, 0.50), (0.50, 0.51), (0.51, 0.51), (0.52, 0.50)]
    lone = (0.10, 0.90)

    assert drop_clusters(cluster + [lone]) == [lone]


def test_the_followed_track_is_kept_when_another_track_gets_longer() -> None:
    from api.rally.shuttle import follow

    tracks: tuple[Track, ...] = ()
    for frame_index in range(6):
        tracks = step(tracks, [(0.2 + 0.01 * frame_index, 0.5)], frame_index)
    position, chosen = follow(tracks, 5, None)
    for frame_index in range(6, 14):
        other = (0.9, 0.1 + 0.02 * (frame_index - 6))
        tracks = step(tracks, [(0.2 + 0.01 * frame_index, 0.5), other], frame_index)
    later, kept = follow(tracks, 13, chosen)

    assert kept is not None and chosen is not None
    assert kept.points[0] == chosen.points[0]
    assert later is not None and later[0] == pytest.approx(0.2 + 0.01 * 13, abs=0.02)
