"""Shared voice/face helpers (probes, template matching, throttles) and the opt-in second factor."""

from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from api.center.audit import audit
from api.center.biometrics import BiometricError, BiometricUnavailable
from api.center.db import get_db
from api.center.handles import key_of
from api.center.throttle import pair_key
from api.center.deps import AuthSession, biometrics_available, check_origin, client_ip, csrf_session, ensure_reauth, settings_of, too_many
from api.center.methods import methods_status
from api.center.models import User
from api.center.schemas import MethodsStatus, SessionOut
from api.center.sessions import begin_session
from api.center.tokens import decode_claims
from api.center.usersessions import checked_method
from sn_shared.security import AuthError

import logging
logger = logging.getLogger(__name__)

UNAVAILABLE = "Biometrics are not available"
BIOMETRIC_FAILED = "Biometric verification failed"
BAD_MFA = "Invalid or expired login session"
BUSY = "Server is busy, try again later"
MAX_AUDIO_BYTES = 3_000_000
MAX_VIDEO_BYTES = 15_000_000
SLOT_WAIT_SECONDS = 5

Upload = Annotated[UploadFile | None, File()]
Text = Annotated[str | None, Form()]
BAD_SAMPLE = "Voice or face sample is unusable, record again"


def ensure_biometrics(request: Request) -> None:
    try:
        if not biometrics_available(request):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("ensure_biometrics failed")
        raise


# 503 first (feature off), then the Origin check.
router = APIRouter(
    prefix="/auth", tags=["biometrics"], dependencies=[Depends(ensure_biometrics), Depends(check_origin)]
)


def read_upload(upload: UploadFile | None, max_bytes: int) -> bytes | None:
    try:
        if upload is None:
            return None
        data = upload.file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File too large")
        return data or None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("read_upload failed")
        raise


@contextmanager
def biometric_slot(request: Request):
    """At most two biometric jobs run at once server-wide; engine errors become plain HTTP errors."""
    slots = request.app.state.biometric_slots
    if not slots.acquire(timeout=SLOT_WAIT_SECONDS):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, BUSY)
    try:
        yield request.app.state.biometrics
    except BiometricError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_SAMPLE) from None
    except BiometricUnavailable as exc:
        audit.error("biometrics unavailable: %s", exc)  # detail stays on the server
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
    finally:
        slots.release()


def read_probes(request: Request, audio: Upload, video: Upload) -> tuple[bytes | None, bytes | None]:
    """(voice, face) embeddings. The voice is the audio file's, or else the clip's own sound track."""
    try:
        audio_raw, video_raw = read_upload(audio, MAX_AUDIO_BYTES), read_upload(video, MAX_VIDEO_BYTES)
        if not audio_raw and not video_raw:
            return None, None
        with biometric_slot(request) as engine:
            face = engine.face_embedding(video_raw) if video_raw else None
            voice = engine.audio_embedding(audio_raw) if audio_raw else voice_from_video(engine, video_raw)
            return voice, face
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("read_probes failed")
        raise


def read_face(request: Request, video: Upload) -> bytes | None:
    """Face embedding of a webcam clip; the clip's sound is never decoded (the webcam method is face only)."""
    try:
        video_raw = read_upload(video, MAX_VIDEO_BYTES)
        if not video_raw:
            return None
        with biometric_slot(request) as engine:
            return engine.face_embedding(video_raw)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("read_face failed")
        raise


def voice_from_video(engine, video_raw: bytes | None) -> bytes | None:
    """A webcam clip carries sound too; a silent clip simply yields no voice sample."""
    if not video_raw:
        return None
    try:
        return engine.audio_embedding(video_raw)
    except BiometricError:
        return None


def factors_match(
    request: Request, user: User, audio: Upload, video: Upload, strict: bool = False, required: tuple[str, ...] | None = None
) -> bool:
    """MFA (required=None): every ENROLLED factor must match. Login: every factor in `required` must be
    enrolled AND match. Any processing error is a plain failure."""
    if required is None and not user.has_biometrics:
        return True
    engine, cipher = request.app.state.biometrics, request.app.state.cipher
    try:
        voice, face = read_probes(request, audio, video)
    except HTTPException as exc:
        audit.warning("biometric login error user=%r status=%s", user.username, exc.status_code)
        return False
    for name, stored, probe, matches in (
        ("voice", user.audio_embedding, voice, engine.audio_matches),
        ("face", user.face_embedding, face, engine.face_matches),
    ):
        if required is not None and name not in required:
            continue
        if not stored:
            if required is not None:
                return False
            continue
        template = cipher.decrypt(stored)
        if probe is None or template is None or not matches(template, probe, strict):
            return False
    return True


def count_attempts(throttles: list, keys: list[str], user_label: str, ip: str) -> None:
    try:
        if any(t.is_blocked(k) for t, k in zip(throttles, keys)):
            audit.warning("biometric login locked user=%r ip=%s", user_label, ip)
            raise too_many()
        for throttle, key in zip(throttles, keys):
            throttle.record(key)  # counted up front (the work is expensive); cleared on success
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("count_attempts failed")
        raise


def reset_throttles(throttles: list, keys: list[str]) -> None:
    try:
        for throttle, key in zip(throttles, keys):
            throttle.reset(key)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("reset_throttles failed")
        raise


@router.post("/login/biometric", response_model=SessionOut)
def login_biometric(
    request: Request,
    response: Response,
    mfa_token: Annotated[str, Form()],
    audio: Upload = None,
    video: Upload = None,
    db: Session = Depends(get_db),
) -> SessionOut:
    """Second factor for accounts that opted in: EVERY enrolled factor must match, one 401 for all failures."""
    ip, state = client_ip(request), request.app.state
    try:
        claims = decode_claims(mfa_token, "mfa")
    except AuthError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_MFA) from None
    user = db.get(User, int(claims["sub"]))
    if user is None or user.token_version != int(claims["ver"]) or user.totp_enabled or not (user.biometric_2fa and user.has_biometrics):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_MFA)  # also: switched off meanwhile, or TOTP is on (it never accepts a biometric instead)
    throttles = [state.bio_throttle, state.bio_account_throttle]
    keys = [pair_key(ip, key_of(user.username)), key_of(user.username)]
    count_attempts(throttles, keys, user.username, ip)
    if not factors_match(request, user, audio, video):
        audit.warning("mfa biometric failed user=%r ip=%s", user.username, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BIOMETRIC_FAILED)
    reset_throttles(throttles, keys)
    audit.info("login ok (biometric 2nd factor) user=%r ip=%s", user.username, ip)
    return begin_session(response, request, db, user, settings_of(request), checked_method(claims.get("mth")))


@router.put("/me/biometric-2fa", response_model=MethodsStatus)
def set_biometric_2fa(
    request: Request,
    enabled: Annotated[bool, Form()],
    password: Text = None,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> MethodsStatus:
    """Opt in/out of voice/face after password or Google sign-in. Needs one sample to turn on; off is always allowed."""
    try:
        user = session.user
        ensure_reauth(request, user, password)
        if enabled and not user.has_biometrics:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enroll a voice or face sample first")
        user.biometric_2fa = enabled
        db.commit()
        audit.info("biometric 2fa %s user=%r ip=%s", "enabled" if enabled else "disabled",
                   user.username, client_ip(request))  # fmt: skip
        return methods_status(user)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("set_biometric_2fa failed")
        raise
