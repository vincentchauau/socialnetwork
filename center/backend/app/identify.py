"""1-N face identification (webcam sign-in without a username) and face uniqueness at enrollment.

Cost: O(N). Every attempt decrypts and compares the template of EVERY webcam-enabled account, so it is
only meant for small deployments (see MAX_IDENTIFY_CANDIDATES). The next step beyond that size is a
vector index (e.g. pgvector / FAISS) holding face vectors, which would also need a different at-rest
protection than per-row Fernet. Plaintext templates are never cached across requests.
"""

import logging
import math
from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User

MAX_IDENTIFY_CANDIDATES = 5000
ENTER_USERNAME = "Enter your username"
FACE_TAKEN = "This face is already registered"
IDENTIFY_GLOBAL_KEY = "all"
_DUMMY_VOICE = bytes(8)  # compared when there is no real template, so the work does not vary

log = logging.getLogger("auth.audit")


@dataclass(frozen=True)
class Identification:
    user: User | None  # set only when the face was accepted unambiguously
    voice_ok: bool  # meaningful only when `user` is set


def _candidates_filter():
    return (User.webcam_login.is_(True), User.face_embedding.is_not(None), User.audio_embedding.is_not(None))


def candidate_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(*_candidates_filter())) or 0


def too_many_candidates(db: Session) -> bool:
    return candidate_count(db) > MAX_IDENTIFY_CANDIDATES


def identify(request: Request, db: Session, face: bytes, voice: bytes | None) -> Identification:
    """Pick the account whose face is closest, require it to be strict and unambiguous, then its voice.

    Always walks every candidate and always runs one voice comparison (against a dummy when needed),
    so the amount of work does not reveal which check failed.
    """
    engine, cipher, settings = request.app.state.biometrics, request.app.state.cipher, request.app.state.settings
    best: User | None = None
    best_distance, second_distance, count = math.inf, math.inf, 0
    for user in db.scalars(select(User).where(*_candidates_filter())):
        template = cipher.decrypt(user.face_embedding)
        if template is None:
            continue
        count += 1
        distance = engine.face_distance(template, face)
        if distance < best_distance:
            best, best_distance, second_distance = user, distance, best_distance
        elif distance < second_distance:
            second_distance = distance
    unambiguous = count == 1 or second_distance - best_distance >= settings.face_identify_margin
    accepted = best is not None and best_distance <= settings.face_threshold_alone and unambiguous
    stored_voice = cipher.decrypt(best.audio_embedding) if best is not None else None
    voice_match = engine.audio_matches(stored_voice or _DUMMY_VOICE, voice or _DUMMY_VOICE, True)
    voice_ok = bool(voice_match and voice is not None and stored_voice is not None)
    return Identification(best if accepted else None, accepted and voice_ok)


def ensure_face_unique(request: Request, db: Session, face: bytes, exclude_user_id: int | None = None) -> None:
    """409 when ANOTHER webcam-enabled account already has (nearly) this face.

    Keeps 1-N identification unambiguous. Privacy trade-off: the 409 tells the caller that a given face
    is registered here. Above MAX_IDENTIFY_CANDIDATES the check is skipped (identification is off there).
    """
    if too_many_candidates(db):
        log.warning("face uniqueness check skipped: more than %d webcam accounts", MAX_IDENTIFY_CANDIDATES)
        return
    engine, cipher, settings = request.app.state.biometrics, request.app.state.cipher, request.app.state.settings
    query = select(User).where(*_candidates_filter())
    if exclude_user_id is not None:
        query = query.where(User.id != exclude_user_id)
    for user in db.scalars(query):
        template = cipher.decrypt(user.face_embedding)
        if template is not None and engine.face_distance(template, face) <= settings.face_threshold_alone:
            raise HTTPException(status.HTTP_409_CONFLICT, FACE_TAKEN)
