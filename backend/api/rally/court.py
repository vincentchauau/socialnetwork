"""The court of a match: four corners picked on the video, and the map from video points to metres.

A point of the video is (x, y) in 0..1 of the frame width and height, so the calibration does not depend on the resolution.
The corners are given in order: near left, near right, far right, far left (the near side is the bottom of the frame).
The doubles court is 13.40 m long and 6.10 m wide; the map sends the corners to (0, 0), (6.10, 0), (6.10, 13.40), (0, 13.40).
"""

import cv2
import numpy as np
from numpy.typing import NDArray

COURT_WIDTH_M = 6.10
COURT_LENGTH_M = 13.40
MIN_AREA = 0.02  # of the whole frame: a court smaller than this is a misclick
Quad = list[list[float]]


def court_corners_m() -> NDArray[np.float32]:
    return np.array(
        [[0.0, 0.0], [COURT_WIDTH_M, 0.0], [COURT_WIDTH_M, COURT_LENGTH_M], [0.0, COURT_LENGTH_M]],
        dtype=np.float32,
    )


def quad_area(corners: Quad) -> float:
    """Shoelace area of the four corners (0..1 of the frame)."""
    total = 0.0
    for index, (x1, y1) in enumerate(corners):
        x2, y2 = corners[(index + 1) % len(corners)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def is_convex(corners: Quad) -> bool:
    """All turns of the outline point the same way: the four corners form a quadrilateral, not a bow tie."""
    signs = []
    for index, (x1, y1) in enumerate(corners):
        x2, y2 = corners[(index + 1) % len(corners)]
        x3, y3 = corners[(index + 2) % len(corners)]
        signs.append((x2 - x1) * (y3 - y2) - (y2 - y1) * (x3 - x2))
    return all(value > 0 for value in signs) or all(value < 0 for value in signs)


def validate_quad(corners: Quad) -> None:
    """Raise ValueError unless the corners are a usable court on the frame."""
    if len(corners) != 4:
        raise ValueError("Mark exactly four corners")
    if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in corners):
        raise ValueError("A corner is outside the video frame")
    if not is_convex(corners):  # first: a bow tie has almost no area, so the size check would mislead
        raise ValueError("The corners are in the wrong order")
    if quad_area(corners) < MIN_AREA:
        raise ValueError("The court is too small on the frame")


def canonical_corners(corners: Quad) -> Quad:
    """The corners in the order near left, near right, far right, far left, whatever order they were clicked in.

    The near side is the lower two points of the frame (larger y); in each pair the left point is the one with the smaller x.
    """
    by_height = sorted(corners, key=lambda point: point[1])
    far = sorted(by_height[:2], key=lambda point: point[0])
    near = sorted(by_height[2:], key=lambda point: point[0])
    return [near[0], near[1], far[1], far[0]]


def court_matrix(corners: Quad) -> NDArray[np.float64]:
    """The 3x3 map from video points (0..1) to metres on the court."""
    validate_quad(corners)
    source = np.array(canonical_corners(corners), dtype=np.float32)
    return np.asarray(cv2.getPerspectiveTransform(source, court_corners_m()), dtype=np.float64)


def to_court(point: tuple[float, float], matrix: NDArray[np.float64]) -> tuple[float, float]:
    """A video point (0..1) in metres on the court: x across the width, y along the length from the near side."""
    x, y = point
    w = matrix[2, 0] * x + matrix[2, 1] * y + matrix[2, 2]
    if abs(w) < 1e-12:
        raise ValueError("The point cannot be placed on the court")
    u = (matrix[0, 0] * x + matrix[0, 1] * y + matrix[0, 2]) / w
    v = (matrix[1, 0] * x + matrix[1, 1] * y + matrix[1, 2]) / w
    return float(u), float(v)


def on_court(point_m: tuple[float, float], margin_m: float = 0.0) -> bool:
    """Is the point (metres) inside the court lines, with an optional margin outside them."""
    x, y = point_m
    return -margin_m <= x <= COURT_WIDTH_M + margin_m and -margin_m <= y <= COURT_LENGTH_M + margin_m
