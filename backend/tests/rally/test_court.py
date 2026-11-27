import pytest

from api.rally.court import (
    COURT_LENGTH_M,
    COURT_WIDTH_M,
    court_matrix,
    on_court,
    quad_area,
    to_court,
    validate_quad,
)

# A court seen as a trapezoid: the far side is narrower than the near side, as in a real broadcast frame.
TRAPEZOID = [[0.1, 0.9], [0.9, 0.9], [0.7, 0.2], [0.3, 0.2]]
SQUARE = [[0.2, 0.8], [0.8, 0.8], [0.8, 0.2], [0.2, 0.2]]


def test_corners_map_to_the_court_corners() -> None:
    matrix = court_matrix(TRAPEZOID)

    mapped = [to_court((x, y), matrix) for x, y in TRAPEZOID]

    expected = [(0.0, 0.0), (COURT_WIDTH_M, 0.0), (COURT_WIDTH_M, COURT_LENGTH_M), (0.0, COURT_LENGTH_M)]
    assert mapped[0] == pytest.approx(expected[0], abs=1e-4)
    assert mapped[1] == pytest.approx(expected[1], abs=1e-4)
    assert mapped[2] == pytest.approx(expected[2], abs=1e-4)
    assert mapped[3] == pytest.approx(expected[3], abs=1e-4)


def test_clicking_the_far_side_first_gives_the_same_court() -> None:
    far_first = [TRAPEZOID[2], TRAPEZOID[3], TRAPEZOID[0], TRAPEZOID[1]]  # far right, far left, near left, near right

    assert to_court((0.1, 0.9), court_matrix(far_first)) == pytest.approx(to_court((0.1, 0.9), court_matrix(TRAPEZOID)), abs=1e-4)
    assert to_court((0.1, 0.9), court_matrix(far_first))[1] == pytest.approx(0.0, abs=1e-4)


def test_saved_court_of_a_match_puts_the_bottom_of_the_frame_near() -> None:
    # The corners of match 1 as they were saved: the far baseline was clicked first.
    saved = [[0.30835828, 0.46248022], [0.68765613, 0.46344805], [0.80093060, 0.89703837], [0.20137683, 0.89800621]]

    near_middle = to_court((0.5, 0.88), court_matrix(saved))
    far_middle = to_court((0.5, 0.47), court_matrix(saved))

    assert near_middle[1] < COURT_LENGTH_M / 2
    assert far_middle[1] > COURT_LENGTH_M / 2


def test_centre_of_a_square_court_is_centre_of_the_court() -> None:
    matrix = court_matrix(SQUARE)

    x, y = to_court((0.5, 0.5), matrix)

    assert x == pytest.approx(COURT_WIDTH_M / 2, abs=1e-4)
    assert y == pytest.approx(COURT_LENGTH_M / 2, abs=1e-4)


def test_on_court_respects_the_lines_and_the_margin() -> None:
    assert on_court((3.0, 6.0))
    assert not on_court((-0.5, 6.0))
    assert on_court((-0.5, 6.0), margin_m=1.0)


def test_area_of_the_square_is_its_side_squared() -> None:
    assert quad_area(SQUARE) == pytest.approx(0.36)


@pytest.mark.parametrize(
    "corners, message",
    [
        ([[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]], "exactly four"),
        ([[0.1, 0.1], [1.2, 0.1], [0.9, 0.9], [0.1, 0.9]], "outside the video frame"),
        ([[0.4, 0.4], [0.6, 0.4], [0.6, 0.45], [0.4, 0.45]], "too small"),
        ([[0.1, 0.1], [0.9, 0.9], [0.9, 0.1], [0.1, 0.9]], "wrong order"),
    ],
)
def test_invalid_corners_are_refused(corners: list[list[float]], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_quad(corners)
