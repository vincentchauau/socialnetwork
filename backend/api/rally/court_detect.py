"""Finds the court on a frame by itself: the green floor is the largest green region, and its outline gives the four corners.

The corners come out in the frame's 0..1 coordinates, in any order (court.canonical_corners sorts them). A frame where no
usable quadrilateral is found gives None, so the sample is skipped rather than placed on a wrong court.
The outline is the floor, not the lines: it is close to the doubles court, not exact.
"""

import cv2
import numpy as np
from numpy.typing import NDArray

from api.rally.court import Quad, quad_area, validate_quad

GREEN_HUE = (35, 90)  # OpenCV hue scale: 0..180
GREEN_MIN_SATURATION = 60
GREEN_MIN_VALUE = 50
MIN_FLOOR_SHARE = 0.05  # the floor is at least this share of the frame
MIN_COURT_SHARE = 0.2  # the court outline covers at least this share of the frame (the whole court is in view)
SIMPLIFY_STEPS = (0.01, 0.02, 0.03, 0.05, 0.08)  # approximation tolerances, as a share of the outline length


def floor_mask(frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower = np.array([GREEN_HUE[0], GREEN_MIN_SATURATION, GREEN_MIN_VALUE], dtype=np.uint8)
    upper = np.array([GREEN_HUE[1], 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    kernel = np.ones((7, 7), dtype=np.uint8)
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)  # the white lines cut the floor: join the pieces
    return cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)


def four_corners(outline: NDArray[np.int32]) -> Quad | None:
    """The outline as four corners: the first simplification with exactly four points."""
    hull = cv2.convexHull(outline)
    perimeter = cv2.arcLength(hull, True)
    for step in SIMPLIFY_STEPS:
        approx = cv2.approxPolyDP(hull, step * perimeter, True)
        if len(approx) == 4:
            return [[float(x), float(y)] for x, y in approx.reshape(-1, 2)]
    return None


def detect_court(frame: NDArray[np.uint8]) -> Quad | None:
    """The four corners of the court on the frame (0..1), or None when the floor cannot be found."""
    height, width = frame.shape[:2]
    contours, _ = cv2.findContours(floor_mask(frame), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < MIN_FLOOR_SHARE * width * height:
        return None
    corners = four_corners(largest)
    if corners is None:
        return None
    normalized = [[x / width, y / height] for x, y in corners]
    try:
        validate_quad(normalized)
    except ValueError:
        return None
    if quad_area(normalized) < MIN_COURT_SHARE:  # a close-up shows a sliver of floor: not the whole court
        return None
    return normalized
