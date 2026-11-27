import cv2
import numpy as np
import pytest

from api.rally.court_detect import detect_court


def frame_with_floor(polygon_px: list[list[int]], size: tuple[int, int] = (480, 640)) -> np.ndarray:
    """A grey frame with a green floor drawn as the polygon (pixels, x then y)."""
    frame = np.full((size[0], size[1], 3), 90, dtype=np.uint8)
    cv2.fillPoly(frame, [np.array(polygon_px, dtype=np.int32)], (60, 180, 60))  # BGR green
    return frame


def test_a_court_in_view_gives_its_four_corners() -> None:
    polygon = [[120, 300], [520, 300], [600, 460], [40, 460]]  # a trapezoid like a court seen from one side
    frame = frame_with_floor(polygon)

    corners = detect_court(frame)

    assert corners is not None
    expected = [[x / 640, y / 480] for x, y in polygon]
    for found, wanted in zip(sorted(corners), sorted(expected)):
        assert found[0] == pytest.approx(wanted[0], abs=0.03)
        assert found[1] == pytest.approx(wanted[1], abs=0.03)


def test_a_small_patch_of_floor_is_not_a_court() -> None:
    frame = frame_with_floor([[300, 200], [340, 200], [340, 230], [300, 230]])

    assert detect_court(frame) is None


def test_a_frame_without_floor_has_no_court() -> None:
    assert detect_court(np.full((480, 640, 3), 90, dtype=np.uint8)) is None

