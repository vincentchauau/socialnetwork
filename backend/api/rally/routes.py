"""The routes of rally: upload a match video, mark its rallies, read the match and its statistics."""

import json
import logging
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from api.rally import stats, store
from api.rally.stats import rallies_csv
from api.rally.db import get_db
from api.rally.job import STATUS_RUNNING, run_analysis, samples_of
from api.rally.models import Match
from api.rally.schemas import CourtIn, MatchOut, MatchSummary, PeopleOut, RallyIn, RallyOut, StatsOut
from api.rally.video import video_response
from sn_shared.limits import reader, writer
from sn_shared.security import TokenPayload

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_VIDEO_SUFFIXES = {".mp4", ".webm", ".mov"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
UNSAFE_CHARACTERS = re.compile(r"[^A-Za-z0-9._-]")
DEFAULT_UPLOAD_DIR = "data/rally"


def upload_dir() -> Path:
    """Where the videos are kept (RALLY_UPLOAD_DIR; each hosted app has its own folder under /data)."""
    try:
        path = Path(os.environ.get("RALLY_UPLOAD_DIR", DEFAULT_UPLOAD_DIR))
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("upload_dir failed")
        raise


def save_upload(upload: UploadFile, target: Path) -> None:
    """Stream the upload to disk. A video above the limit is refused and its partial file removed."""
    written = 0
    try:
        with target.open("wb") as handle:
            while chunk := upload.file.read(UPLOAD_CHUNK_BYTES):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="The video is larger than 2 GB")
                handle.write(chunk)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except OSError as error:
        logger.exception("save_upload failed")
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="The video could not be saved") from error


def court_of(match: Match) -> list[list[float]] | None:
    return json.loads(match.court_corners) if match.court_corners else None


def match_out(match: Match, db: Session) -> MatchOut:
    rallies = store.list_rallies(db, match.id)
    return MatchOut(
        id=match.id,
        name=match.name,
        video_name=match.video_name,
        created_at=match.created_at,
        rallies=[RallyOut.model_validate(rally, from_attributes=True) for rally in rallies],
        stats=StatsOut(**stats.summary(rallies)),
        court=court_of(match),
    )


@router.get("/matches", response_model=list[MatchSummary])
def list_matches(user: TokenPayload = Depends(reader), db: Session = Depends(get_db)) -> list[Match]:
    try:
        return store.list_matches(db, user.user_id)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("list_matches failed")
        raise


@router.post("/matches", status_code=201, response_model=MatchSummary)
def upload_match(
    name: Annotated[str, Form(min_length=1, max_length=100)],
    video: Annotated[UploadFile, File()],
    user: TokenPayload = Depends(writer),
    db: Session = Depends(get_db),
) -> Match:
    try:
        suffix = Path(video.filename or "").suffix.lower()
        if suffix not in ALLOWED_VIDEO_SUFFIXES:
            raise HTTPException(status_code=415, detail="Use an mp4, webm or mov video")
        safe_name = UNSAFE_CHARACTERS.sub("_", Path(video.filename or "video").name)
        target = upload_dir() / f"{uuid.uuid4().hex}_{safe_name}"
        save_upload(video, target)
        match = Match(user_id=user.user_id, name=name.strip(), video_name=safe_name, video_path=str(target))
        db.add(match)
        db.commit()
        return match
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("upload_match failed")
        raise


@router.get("/matches/{match_id}", response_model=MatchOut)
def read_match(match_id: int, user: TokenPayload = Depends(reader), db: Session = Depends(get_db)) -> MatchOut:
    try:
        return match_out(store.owned_match(db, user.user_id, match_id), db)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("read_match failed")
        raise


@router.put("/matches/{match_id}/court", response_model=MatchOut)
def set_court(match_id: int, body: CourtIn, user: TokenPayload = Depends(writer), db: Session = Depends(get_db)) -> MatchOut:
    try:
        match = store.owned_match(db, user.user_id, match_id)
        match.court_corners = json.dumps(body.corners)
        db.commit()
        return match_out(match, db)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("set_court failed")
        raise


@router.post("/matches/{match_id}/people", status_code=202, response_model=PeopleOut)
def start_people(match_id: int, request: Request, user: TokenPayload = Depends(writer), db: Session = Depends(get_db)) -> PeopleOut:
    try:
        match = store.owned_match(db, user.user_id, match_id)
        if match.people_status == STATUS_RUNNING:
            raise HTTPException(status_code=409, detail="The players are already being found")
        match.people_status = STATUS_RUNNING
        db.commit()
        threading.Thread(target=run_analysis, args=(request.app.state.session_factory, match_id), daemon=True).start()
        return PeopleOut(status=STATUS_RUNNING, samples=[])
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("start_people failed")
        raise


@router.get("/matches/{match_id}/people", response_model=PeopleOut)
def read_people(match_id: int, user: TokenPayload = Depends(reader), db: Session = Depends(get_db)) -> PeopleOut:
    try:
        match = store.owned_match(db, user.user_id, match_id)
        return PeopleOut(status=match.people_status, samples=samples_of(match))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("read_people failed")
        raise


@router.get("/matches/{match_id}/export.csv")
def export_rallies(match_id: int, user: TokenPayload = Depends(reader), db: Session = Depends(get_db)) -> Response:
    try:
        match = store.owned_match(db, user.user_id, match_id)
        body = rallies_csv(store.list_rallies(db, match.id))
        filename = f"rallies-{match.id}.csv"
        return Response(content=body, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("export_rallies failed")
        raise


@router.get("/matches/{match_id}/video")
def stream_video(match_id: int, request: Request, user: TokenPayload = Depends(reader), db: Session = Depends(get_db)) -> Response:
    try:
        match = store.owned_match(db, user.user_id, match_id)
        path = Path(match.video_path)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="The video file is missing")
        return video_response(path, request)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("stream_video failed")
        raise


@router.post("/matches/{match_id}/rallies", status_code=201, response_model=RallyOut)
def add_rally(match_id: int, body: RallyIn, user: TokenPayload = Depends(writer), db: Session = Depends(get_db)) -> RallyOut:
    try:
        store.owned_match(db, user.user_id, match_id)
        rally = store.add_rally(db, match_id, body)
        db.commit()
        return RallyOut.model_validate(rally, from_attributes=True)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("add_rally failed")
        raise


@router.delete("/matches/{match_id}/rallies/{rally_id}", status_code=204)
def remove_rally(match_id: int, rally_id: int, user: TokenPayload = Depends(writer), db: Session = Depends(get_db)) -> Response:
    try:
        store.owned_match(db, user.user_id, match_id)
        if not store.delete_rally(db, match_id, rally_id):
            raise HTTPException(status_code=404, detail="Rally not found")
        db.commit()
        return Response(status_code=204)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("remove_rally failed")
        raise
