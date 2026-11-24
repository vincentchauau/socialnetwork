"""Face: read frames sequentially, downscale, 128-d face_recognition vectors, averaged."""

import os
import tempfile
import time

from api.center.biometrics import BiometricError, BiometricUnavailable

FRAME_STRIDE = 5  # one frame in five
MAX_WIDTH = 480
MAX_READ = 600  # never read more frames than this, however long the video
MAX_PIXELS = 4096 * 4096  # larger frames are rejected before allocating more memory
TIME_BUDGET = 20.0  # seconds for the whole video


def _libs():
    try:
        import cv2
        import face_recognition
        import numpy
    except ImportError as exc:
        raise BiometricUnavailable("opencv-python, numpy and face_recognition (dlib) are required") from exc
    return cv2, face_recognition, numpy


def embed_face(raw: bytes, max_frames: int, clock=time.monotonic) -> bytes:
    cv2, face_recognition, np = _libs()
    fd, path = tempfile.mkstemp(suffix=".webm")  # reopenable by name on Windows
    started = clock()
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise BiometricError("Could not open the video")
        vectors, attempts = [], 0
        try:
            for index in range(MAX_READ):
                if clock() - started > TIME_BUDGET:
                    raise BiometricError("Video processing took too long")
                ok, frame = cap.read()
                if not ok:
                    break
                if index % FRAME_STRIDE:
                    continue
                height, width = frame.shape[:2]
                if height * width > MAX_PIXELS:
                    raise BiometricError("Video frame is too large")
                scale = min(1.0, MAX_WIDTH / width)
                if scale < 1.0:
                    frame = cv2.resize(frame, None, fx=scale, fy=scale)
                attempts += 1  # every encoding costs CPU, including frames with 0 or many faces
                encodings = face_recognition.face_encodings(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                if len(encodings) == 1:
                    vectors.append(encodings[0])
                if len(vectors) >= max_frames or attempts >= max_frames * 2:
                    break
        finally:
            cap.release()
    finally:
        os.unlink(path)
    if not vectors:
        raise BiometricError("Exactly one face must be visible in the video")
    return np.asarray(np.mean(vectors, axis=0), dtype=np.float32).tobytes()
