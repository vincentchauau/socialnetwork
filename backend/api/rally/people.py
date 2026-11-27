"""Players on the court: a person detector (YOLOv8n, ONNX, run by OpenCV) and the position of each person on the court.

The detector gives boxes in a 640 x 640 input; the box's bottom-centre (the feet) is the point that is mapped onto the court.
A person is kept when the feet are on the court (with a margin for the lines). The side names are the half and the side:
"near-left" (the bottom of the frame, left), "far-right" and so on. Players change ends in a match, so no label is a player.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from api.rally.court import COURT_LENGTH_M, COURT_WIDTH_M, court_matrix, on_court, to_court
from api.rally.court_detect import detect_court

INPUT_SIZE = 640
PERSON_CLASS = 4  # the score of class 0 (person) sits after the four box values
CONFIDENCE = 0.35
NMS_THRESHOLD = 0.45
COURT_MARGIN_M = 1.0  # feet this far outside the lines still count (the lines are drawn on the floor, not the feet)


@dataclass(frozen=True)
class Person:
    foot_x: float  # 0..1 of the frame width
    foot_y: float  # 0..1 of the frame height
    score: float


def decode(raw: NDArray[np.float32]) -> list[Person]:
    """The people in one YOLOv8 output (84 x 8400, or 8400 x 84): boxes after the confidence cut and non-maximum suppression."""
    table = raw.T if raw.shape[0] == PERSON_CLASS + 80 else raw
    cx, cy, width, height = table[:, 0], table[:, 1], table[:, 2], table[:, 3]
    scores = table[:, PERSON_CLASS]
    keep = np.flatnonzero(scores >= CONFIDENCE)
    if keep.size == 0:
        return []
    boxes = [[float(cx[i] - width[i] / 2), float(cy[i] - height[i] / 2), float(width[i]), float(height[i])] for i in keep]
    chosen = cv2.dnn.NMSBoxes(boxes, [float(scores[i]) for i in keep], CONFIDENCE, NMS_THRESHOLD)
    people = []
    for index in np.array(chosen).reshape(-1):
        i = keep[index]
        people.append(Person(
            foot_x=float(cx[i]) / INPUT_SIZE,
            foot_y=float(cy[i] + height[i] / 2) / INPUT_SIZE,
            score=float(scores[i]),
        ))
    return people


def detect(net: cv2.dnn.Net, frame: NDArray[np.uint8]) -> list[Person]:
    blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (INPUT_SIZE, INPUT_SIZE), swapRB=True, crop=False)
    net.setInput(blob)
    raw = np.asarray(net.forward())[0]
    return decode(raw)


def side_name(point_m: tuple[float, float]) -> str:
    """The half and the side of a point on the court, in metres."""
    x, y = point_m
    half = "near" if y < COURT_LENGTH_M / 2 else "far"
    side = "left" if x < COURT_WIDTH_M / 2 else "right"
    return f"{half}-{side}"


def on_court_people(people: list[Person], matrix: NDArray[np.float64]) -> list[dict[str, float | str]]:
    """The people whose feet are on the court, with their position in metres and their side."""
    placed = []
    for person in people:
        point = to_court((person.foot_x, person.foot_y), matrix)
        if not on_court(point, COURT_MARGIN_M):
            continue
        placed.append({
            "side": side_name(point),
            "x_m": round(point[0], 2),
            "y_m": round(point[1], 2),
            "x": round(person.foot_x, 4),  # the feet on the frame (0..1), to draw them over the video
            "y": round(person.foot_y, 4),
            "score": round(person.score, 2),
        })
    return placed


def load_detector(path: str) -> cv2.dnn.Net:
    return cv2.dnn.readNetFromONNX(path)


def sample_of(frame: NDArray[np.uint8], net: cv2.dnn.Net) -> dict[str, object]:
    """The court and the people on it in one frame. Without a court found in the frame, nobody is placed."""
    corners = detect_court(frame)
    if corners is None:
        return {"court": None, "people": []}
    matrix = court_matrix(corners)
    return {"court": corners, "people": on_court_people(detect(net, frame), matrix)}


def track(video_path: str, net: cv2.dnn.Net, step_ms: int) -> list[dict[str, object]]:
    """One sample every `step_ms` of the video: the time, the court found on that frame and the people on it."""
    capture = cv2.VideoCapture(video_path)
    try:
        if not capture.isOpened():
            raise ValueError(f"The video cannot be opened: {video_path}")
        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        every = max(1, round(fps * step_ms / 1000))
        samples: list[dict[str, object]] = []
        index = 0
        while capture.grab():
            if index % every == 0:
                ok, frame = capture.retrieve()
                if ok:
                    samples.append({"t_ms": round(index * 1000 / fps), **sample_of(frame, net)})
            index += 1
        return samples
    finally:
        capture.release()
