import numpy as np
import pytest

from api.rally.court import court_matrix
from api.rally.people import decode, on_court_people, side_name

SQUARE = [[0.2, 0.8], [0.8, 0.8], [0.8, 0.2], [0.2, 0.2]]


def output_with(boxes: list[tuple[int, float, float, float, float, float]]) -> np.ndarray:
    """A YOLOv8 output (84 x 8400) with one person per (anchor, cx, cy, w, h, score)."""
    raw = np.zeros((84, 8400), dtype=np.float32)
    for anchor, cx, cy, width, height, score in boxes:
        raw[0:4, anchor] = [cx, cy, width, height]
        raw[4, anchor] = score
    return raw


def test_decode_keeps_one_person_per_overlapping_box() -> None:
    raw = output_with([(5, 320, 320, 100, 200, 0.9), (6, 322, 318, 100, 200, 0.8)])

    people = decode(raw)

    assert len(people) == 1
    assert people[0].foot_x == pytest.approx(0.5)
    assert people[0].foot_y == pytest.approx(420 / 640)
    assert people[0].score == pytest.approx(0.9, abs=1e-6)


def test_decode_drops_low_confidence_and_distant_boxes() -> None:
    raw = output_with([(5, 100, 100, 50, 80, 0.1), (9, 500, 500, 60, 90, 0.7)])

    people = decode(raw)

    assert len(people) == 1
    assert people[0].foot_x == pytest.approx(500 / 640)


def test_decode_nothing_when_no_person() -> None:
    assert decode(np.zeros((84, 8400), dtype=np.float32)) == []


@pytest.mark.parametrize(
    "point, expected",
    [
        ((1.0, 1.0), "near-left"),
        ((5.0, 1.0), "near-right"),
        ((1.0, 12.0), "far-left"),
        ((5.0, 12.0), "far-right"),
    ],
)
def test_side_name_names_the_half_and_the_side(point: tuple[float, float], expected: str) -> None:
    assert side_name(point) == expected


def test_people_on_the_court_are_placed_and_others_dropped() -> None:
    matrix = court_matrix(SQUARE)
    from api.rally.people import Person

    people = [
        Person(foot_x=0.25, foot_y=0.75, score=0.9),  # near left, on the court
        Person(foot_x=0.05, foot_y=0.5, score=0.8),  # far outside the left line: the umpire or a spectator
    ]

    placed = on_court_people(people, matrix)

    assert len(placed) == 1
    assert placed[0]["side"] == "near-left"
    assert placed[0]["x_m"] == pytest.approx(0.51, abs=0.01)
    assert placed[0]["y_m"] == pytest.approx(1.12, abs=0.01)
