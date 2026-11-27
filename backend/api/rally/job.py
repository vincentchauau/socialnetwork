"""The players job: runs the detector over a match video in a background thread and keeps the result on the match.

Status of a match: "idle" (never run), "running", "done" or "failed". The result is the list of samples (see people.track).
"""

import json
import logging
import os
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from api.rally.models import Match
from api.rally.people import load_detector, track

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PATH = "data/models/yolov8n.onnx"
SAMPLE_STEP_MS = 500  # two samples a second are enough to follow players and draw them
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_IDLE = "idle"


def model_path() -> str:
    return os.environ.get("RALLY_MODEL_PATH", DEFAULT_MODEL_PATH)


def set_status(factory: sessionmaker[Session], match_id: int, status: str, track_json: str | None = None) -> None:
    """Write the status (and the result, when there is one) in its own session."""
    try:
        with factory() as db:
            match = db.get(Match, match_id)
            if match is None:
                return
            match.people_status = status
            if track_json is not None:
                match.people_track = track_json
            db.commit()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("set_status failed")
        raise


def run_analysis(factory: sessionmaker[Session], match_id: int) -> None:
    """The job itself: detect the players on every sample of the video, then store the samples."""
    try:
        with factory() as db:
            match = db.get(Match, match_id)
            if match is None:
                set_status(factory, match_id, STATUS_FAILED)
                return
            video_path = match.video_path
        samples = track(video_path, load_detector(model_path()), SAMPLE_STEP_MS)
        set_status(factory, match_id, STATUS_DONE, json.dumps(samples))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("run_analysis failed")
        set_status(factory, match_id, STATUS_FAILED)


def samples_of(match: Match) -> list[dict[str, Any]]:
    return json.loads(match.people_track) if match.people_track else []
