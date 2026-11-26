"""1-N identification (webcam or voice sign-in without a username) and uniqueness at enrollment.

Cost: O(N). Every attempt decrypts and compares the template of EVERY enabled account, so it is only
meant for small deployments (see MAX_IDENTIFY_CANDIDATES). The next step beyond that size is a vector
index (e.g. pgvector / FAISS) holding the vectors, which would also need a different at-rest protection
than per-row Fernet. Plaintext templates are never cached across requests.

Both modalities share one engine: a "cost" where LOWER is better (face distance, or minus the cosine
similarity of voices), so the threshold and the runner-up margin work the same way for each.
"""

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.center.config import Settings
from api.center.models import User

logger = logging.getLogger(__name__)

MAX_IDENTIFY_CANDIDATES = 5000
ENTER_USERNAME = "Enter your username"
FACE_TAKEN = "This face is already registered"
VOICE_TAKEN = "This voice is already registered"
IDENTIFY_GLOBAL_KEY = "all"

log = logging.getLogger("auth.audit")


@dataclass(frozen=True)
class Modality:
    """What differs between face and voice identification."""

    name: str
    flag: str  # User column: sign-in method enabled
    column: str  # User column: encrypted template
    dummy: bytes  # compared when there is no candidate, so the work does not vary
    taken: str
    cost: Callable[[object, bytes, bytes], float]  # (engine, stored, probe) -> lower is better
    limit: Callable[[Settings], float]  # a match must have cost <= limit
    margin: Callable[[Settings], float]  # best must beat the runner-up by at least this

    def filters(self) -> tuple:
        try:
            return (getattr(User, self.flag).is_(True), getattr(User, self.column).is_not(None), User.kind == "human")
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("filters failed")
            raise


# Placeholders must be well-formed templates for the REAL engine (a malformed one used to crash it and
# turn this into a 500): 128 float32 zeros for a face; 256 float32 ones for a voice (non-zero norm).
DUMMY_FACE = bytes(128 * 4)
DUMMY_VOICE = bytes([0x00, 0x00, 0x80, 0x3F]) * 256  # float32 1.0 x 256

FACE = Modality(
    name="face", flag="webcam_login", column="face_embedding", dummy=DUMMY_FACE, taken=FACE_TAKEN,
    cost=lambda engine, stored, probe: engine.face_distance(stored, probe),
    limit=lambda s: s.face_threshold_alone,
    margin=lambda s: s.face_identify_margin,
)  # fmt: skip
VOICE = Modality(
    name="voice", flag="voice_login", column="audio_embedding", dummy=DUMMY_VOICE, taken=VOICE_TAKEN,
    cost=lambda engine, stored, probe: -engine.audio_similarity(stored, probe),
    limit=lambda s: -s.audio_threshold_alone,
    margin=lambda s: s.voice_identify_margin,
)  # fmt: skip


def candidate_count(db: Session, kind: Modality = FACE) -> int:
    try:
        return db.scalar(select(func.count()).select_from(User).where(*kind.filters())) or 0
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("candidate_count failed")
        raise


def too_many_candidates(db: Session, kind: Modality = FACE) -> bool:
    try:
        return candidate_count(db, kind) > MAX_IDENTIFY_CANDIDATES
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("too_many_candidates failed")
        raise


def identify_identify(request: Request, db: Session, kind: Modality, probe: bytes) -> User | None:
    """The account closest to the probe, if that match is strict and unambiguous; else None.

    The probe is the only factor. Always walks every candidate (and runs one dummy comparison when there
    is none), so the amount of work does not reveal which check failed.
    """
    try:
        engine, cipher, settings = request.app.state.biometrics, request.app.state.cipher, request.app.state.settings
        best: User | None = None
        best_cost, second_cost, count = math.inf, math.inf, 0
        for user in db.scalars(select(User).where(*kind.filters())):
            template = cipher.decrypt(getattr(user, kind.column))
            if template is None:
                continue
            count += 1
            cost = kind.cost(engine, template, probe)
            if cost < best_cost:
                best, best_cost, second_cost = user, cost, best_cost
            elif cost < second_cost:
                second_cost = cost
        if count == 0:
            kind.cost(engine, kind.dummy, probe)
        unambiguous = count == 1 or second_cost - best_cost >= kind.margin(settings)
        accepted = best is not None and best_cost <= kind.limit(settings) and unambiguous
        return best if accepted else None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("identify_identify failed")
        raise


def identify(request: Request, db: Session, face: bytes) -> User | None:
    """Webcam sign-in without a username: the account whose face is closest, if strict and unambiguous."""
    try:
        return identify_identify(request, db, FACE, face)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("identify failed")
        raise


def identify_voice(request: Request, db: Session, voice: bytes) -> User | None:
    """Voice sign-in without a username: the account whose voice is closest, if strict and unambiguous."""
    try:
        return identify_identify(request, db, VOICE, voice)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("identify_voice failed")
        raise


def ensure_unique(
    request: Request, db: Session, kind: Modality, probe: bytes, exclude_user_id: int | None
) -> None:
    """409 when ANOTHER account with this method enabled already has (nearly) this template.

    Keeps 1-N identification unambiguous. Privacy trade-off: the 409 tells the caller that a given face or
    voice is registered here. Above MAX_IDENTIFY_CANDIDATES the check is skipped (identification is off).
    """
    try:
        if too_many_candidates(db, kind):
            log.warning("%s uniqueness check skipped: more than %d accounts", kind.name, MAX_IDENTIFY_CANDIDATES)
            return
        engine, cipher, settings = request.app.state.biometrics, request.app.state.cipher, request.app.state.settings
        query = select(User).where(*kind.filters())
        if exclude_user_id is not None:
            query = query.where(User.id != exclude_user_id)
        for user in db.scalars(query):
            template = cipher.decrypt(getattr(user, kind.column))
            if template is not None and kind.cost(engine, template, probe) <= kind.limit(settings):
                raise HTTPException(status.HTTP_409_CONFLICT, kind.taken)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("ensure_unique failed")
        raise


def ensure_face_unique(request: Request, db: Session, face: bytes, exclude_user_id: int | None = None) -> None:
    try:
        ensure_unique(request, db, FACE, face, exclude_user_id)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("ensure_face_unique failed")
        raise


def ensure_voice_unique(request: Request, db: Session, voice: bytes, exclude_user_id: int | None = None) -> None:
    try:
        ensure_unique(request, db, VOICE, voice, exclude_user_id)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("ensure_voice_unique failed")
        raise
