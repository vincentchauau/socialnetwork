"""1-N face identification (webcam sign-in without a username) and face uniqueness at enrollment.

Cost: O(N). Every attempt decrypts and compares the template of EVERY webcam-enabled account, so it is
only meant for small deployments (see MAX_IDENTIFY_CANDIDATES). The next step beyond that size is a
vector index (e.g. pgvector / FAISS) holding face vectors, which would also need a different at-rest
protection than per-row Fernet. Plaintext templates are never cached across requests.
"""

import logging
import math

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User

MAX_IDENTIFY_CANDIDATES = 5000
ENTER_USERNAME = "Enter your username"
FACE_TAKEN = "This face is already registered"
IDENTIFY_GLOBAL_KEY = "all"
# Compared when there is no candidate, so the work does not vary. It must be a well-formed template
# (128 float32 values): a malformed one used to crash the real engine and turn this into a 500.
_DUMMY_FACE = bytes(128 * 4)

log = logging.getLogger("auth.audit")


def _candidates_filter():
    return (User.webcam_login.is_(True), User.face_embedding.is_not(None))


def candidate_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(*_candidates_filter())) or 0


def too_many_candidates(db: Session) -> bool:
    return candidate_count(db) > MAX_IDENTIFY_CANDIDATES


def identify(request: Request, db: Session, face: bytes) -> User | None:
    """The account whose face is closest, if that match is strict and unambiguous; else None.

    The face is the only factor. Always walks every candidate (and runs one dummy comparison when there
    is none), so the amount of work does not reveal which check failed.
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
    if count == 0:
        engine.face_distance(_DUMMY_FACE, face)
    unambiguous = count == 1 or second_distance - best_distance >= settings.face_identify_margin
    accepted = best is not None and best_distance <= settings.face_threshold_alone and unambiguous
    return best if accepted else None


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
