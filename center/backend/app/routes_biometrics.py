"""Voice + face: opt-in passwordless login (never a second factor) and enrollment management."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.biometrics import BiometricError, BiometricUnavailable
from app.db import get_db
from app.deps import AuthSession, check_origin, client_ip, csrf_session, require_reauth, settings_of, too_many
from app.models import User
from app.schemas import BiometricStatus, SessionOut
from app.sessions import issue_session

UNAVAILABLE = "Biometrics are not available"
BIO_ONLY_FAILED = "Biometric login failed"
BUSY = "Server is busy, try again later"
MAX_AUDIO_BYTES = 3_000_000
MAX_VIDEO_BYTES = 15_000_000
SLOT_WAIT_SECONDS = 5

Upload = Annotated[UploadFile | None, File()]
Text = Annotated[str | None, Form()]


def require_biometrics(request: Request) -> None:
    if not settings_of(request).biometrics_enabled or request.app.state.biometrics is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE)


# 503 first (feature off), then the Origin check.
router = APIRouter(
    prefix="/auth", tags=["biometrics"], dependencies=[Depends(require_biometrics), Depends(check_origin)]
)


def read_upload(upload: UploadFile | None, max_bytes: int) -> bytes | None:
    if upload is None:
        return None
    data = upload.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large")
    return data or None


def read_probes(request: Request, audio: Upload, video: Upload) -> tuple[bytes | None, bytes | None]:
    """(voice, face) embeddings; at most two biometric jobs run at once server-wide."""
    engine = request.app.state.biometrics
    audio_raw, video_raw = read_upload(audio, MAX_AUDIO_BYTES), read_upload(video, MAX_VIDEO_BYTES)
    if not audio_raw and not video_raw:
        return None, None
    slots = request.app.state.biometric_slots
    if not slots.acquire(timeout=SLOT_WAIT_SECONDS):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, BUSY)
    try:
        face = engine.face_embedding(video_raw) if video_raw else None
        if audio_raw:
            voice = engine.audio_embedding(audio_raw)
        else:
            voice = _voice_from_video(engine, video_raw)
        return voice, face
    except BiometricError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Voice or face sample is unusable, record again") from None
    except BiometricUnavailable as exc:
        audit.error("biometrics unavailable: %s", exc)  # detail stays on the server
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
    finally:
        slots.release()


def _voice_from_video(engine, video_raw: bytes | None) -> bytes | None:
    """A webcam clip carries sound too; a silent clip simply yields no voice sample."""
    if not video_raw:
        return None
    try:
        return engine.audio_embedding(video_raw)
    except BiometricError:
        return None


def factors_match(request: Request, user: User, audio: Upload, video: Upload, strict: bool = False) -> bool:
    """True only if EVERY enrolled factor matches. Any processing error is a plain failure."""
    if not user.has_biometrics:
        return True
    engine, cipher = request.app.state.biometrics, request.app.state.cipher
    try:
        voice, face = read_probes(request, audio, video)
    except HTTPException as exc:
        audit.warning("biometric login error user=%r status=%s", user.username, exc.status_code)
        return False
    for stored, probe, matches in (
        (user.audio_embedding, voice, engine.audio_matches),
        (user.face_embedding, face, engine.face_matches),
    ):
        if not stored:
            continue
        template = cipher.decrypt(stored)
        if probe is None or template is None or not matches(template, probe, strict):
            return False
    return True


def _count_attempts(throttles: list, keys: list[str], user_label: str, ip: str) -> None:
    if any(t.is_blocked(k) for t, k in zip(throttles, keys)):
        audit.warning("biometric login locked user=%r ip=%s", user_label, ip)
        raise too_many()
    for throttle, key in zip(throttles, keys):
        throttle.record(key)  # counted up front (the work is expensive); cleared on success


def _reset(throttles: list, keys: list[str]) -> None:
    for throttle, key in zip(throttles, keys):
        throttle.reset(key)


@router.post("/login/biometric-only", response_model=SessionOut)
def login_biometric_only(
    request: Request,
    response: Response,
    username: Annotated[str, Form(max_length=64)],
    audio: Upload = None,
    video: Upload = None,
    db: Session = Depends(get_db),
) -> SessionOut:
    """Passwordless login for accounts that opted in: both samples, strict thresholds, one 401 for all failures."""
    ip, state, name = client_ip(request), request.app.state, username.strip().lower()
    throttles = [state.alone_throttle, state.alone_account_throttle]
    keys = [f"{ip}|{name}", name]
    _count_attempts(throttles, keys, name, ip)
    user = db.scalar(select(User).where(User.username == name))
    if (
        user is None
        or not user.biometric_login
        or not (user.audio_embedding and user.face_embedding)
        or not factors_match(request, user, audio, video, strict=True)
    ):
        audit.warning("biometric-only login failed user=%r ip=%s", name, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BIO_ONLY_FAILED)
    _reset(throttles, keys)
    audit.info("login ok (biometric only) user=%r ip=%s", name, ip)
    return issue_session(response, user, settings_of(request))


def _status(user: User) -> BiometricStatus:
    return BiometricStatus(
        has_audio=bool(user.audio_embedding),
        has_face=bool(user.face_embedding),
        biometric_login=user.biometric_login,
        passwordless_ready=bool(user.audio_embedding and user.face_embedding),
    )


@router.post("/me/biometrics", response_model=BiometricStatus)
def enroll(
    request: Request,
    password: Text = None,
    audio: Upload = None,
    video: Upload = None,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> BiometricStatus:
    """Add or replace the voice and/or face template (only the samples you send are replaced).

    One factor can be enrolled now and the other later, but passwordless login needs both.
    """
    user, throttle = session.user, request.app.state.enroll_throttle
    if throttle.is_blocked(str(user.id)):
        raise too_many()
    require_reauth(request, user, password)
    throttle.record(str(user.id))  # expensive: every call counts
    voice, face = read_probes(request, audio, video)
    if voice is None and face is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Send at least one audio or video recording")
    cipher = request.app.state.cipher
    if voice is not None:
        user.audio_embedding = cipher.encrypt(voice)
    if face is not None:
        user.face_embedding = cipher.encrypt(face)
    db.commit()
    audit.info(
        "biometrics enrolled user=%r ip=%s audio=%s face=%s",
        user.username, client_ip(request), voice is not None, face is not None,
    )  # fmt: skip
    return _status(user)


@router.put("/me/biometric-login", response_model=BiometricStatus)
def set_biometric_login(
    request: Request,
    enabled: Annotated[bool, Form()],
    password: Text = None,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> BiometricStatus:
    user = session.user
    require_reauth(request, user, password)
    if enabled and not (user.audio_embedding and user.face_embedding):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Enroll both voice and face first")
    user.biometric_login = enabled
    db.commit()
    audit.info("biometric-only login %s user=%r ip=%s", "enabled" if enabled else "disabled",
               user.username, client_ip(request))  # fmt: skip
    return _status(user)


@router.delete("/me/biometrics", response_model=BiometricStatus)
def delete_biometrics(
    request: Request,
    password: Text = None,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> BiometricStatus:
    user = session.user
    require_reauth(request, user, password)
    user.audio_embedding = None
    user.face_embedding = None
    user.biometric_login = False
    db.commit()
    audit.info("biometrics deleted user=%r ip=%s", user.username, client_ip(request))
    return _status(user)
