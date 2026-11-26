"""Real-engine liveness: sample the clip (~12 fps, capped), landmarks per frame, then the pure checks of
app.liveness. NEVER raises: malformed, short or empty video simply yields no actions."""

import logging
import os
import tempfile
import time

from api.center import liveness as lv

logger = logging.getLogger(__name__)

audit = logging.getLogger("auth.audit")

TARGET_FPS = 12
DEFAULT_FPS = 30.0
MAX_ANALYSED_FRAMES = 90
MAX_READ = 600
MAX_WIDTH = 320
MAX_PIXELS = 4096 * 4096
TIME_BUDGET = 20.0


def points(landmark) -> list[tuple[float, float]]:
    try:
        return [(float(x), float(y)) for x, y in landmark]
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("points failed")
        raise


def frame_features(marks: dict) -> tuple[float, float, float]:
    """(ear, mar, yaw) of one face's face_recognition landmarks."""
    try:
        ear = (lv.eye_aspect_ratio(points(marks["left_eye"])) + lv.eye_aspect_ratio(points(marks["right_eye"]))) / 2
        mar = lv.mouth_aspect_ratio(points(marks["top_lip"]), points(marks["bottom_lip"]))
        return ear, mar, lv.yaw_proxy(points(marks["nose_bridge"]), points(marks["chin"]))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("frame_features failed")
        raise


def liveness_actions(raw: bytes, clock=time.monotonic) -> list[str]:
    try:
        return analyse(raw, clock)
    except Exception as exc:  # noqa: BLE001 - liveness must never take a request down
        audit.warning("liveness analysis error: %s", type(exc).__name__)
        return []


def analyse(raw: bytes, clock) -> list[str]:
    if not raw:
        return []
    import cv2
    import face_recognition
    import numpy as np

    fd, path = tempfile.mkstemp(suffix=".webm")
    started = clock()
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return []
        fps = cap.get(cv2.CAP_PROP_FPS) or DEFAULT_FPS
        stride = max(1, round((fps if 1 <= fps <= 120 else DEFAULT_FPS) / TARGET_FPS))
        features, boxes, counts, first, last = [], [], [], None, None
        try:
            for index in range(MAX_READ):
                if clock() - started > TIME_BUDGET or len(counts) >= MAX_ANALYSED_FRAMES:
                    break
                ok, frame = cap.read()
                if not ok:
                    break
                if index % stride:
                    continue
                height, width = frame.shape[:2]
                if height * width > MAX_PIXELS:
                    return []
                if width > MAX_WIDTH:
                    frame = cv2.resize(frame, None, fx=MAX_WIDTH / width, fy=MAX_WIDTH / width)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                locations = face_recognition.face_locations(rgb)
                counts.append(len(locations))
                if len(locations) != 1:
                    continue
                marks = face_recognition.face_landmarks(rgb, locations)
                if not marks:
                    continue
                features.append(frame_features(marks[0]))
                boxes.append(locations[0])
                if first is None:
                    first = (rgb, locations)
                last = (rgb, locations)
        finally:
            cap.release()
        if not lv.face_present_enough(counts) or not lv.has_motion(boxes) or first is None or last is None:
            return []
        a = face_recognition.face_encodings(first[0], first[1])
        b = face_recognition.face_encodings(last[0], last[1])
        if not a or not b or not lv.same_person(list(np.asarray(a[0])), list(np.asarray(b[0]))):
            return []
        return lv.detect_actions(features)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
