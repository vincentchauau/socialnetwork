"""Voice and webcam sign-in: register with them, sign in with them, link and remove them.

Re-auth rule: linking/removing asks for the password only when the account HAS one. Accounts without
a password (voice, webcam or Google only) have nothing to re-enter, so no re-auth is asked for them:
a stolen session of such an account can change its methods (known limitation).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_db
from app.deps import AuthSession, biometrics_available, check_origin, client_ip, csrf_session, require_reauth, settings_of, too_many
from app.methods import GOOGLE_IN_USE, KEEP_ONE, methods_status, usable_methods
from app.models import User
from app.passwords import NO_PASSWORD, hash_password, password_problem
from app.routes_auth import verify_google_or_throttle
from app.routes_biometrics import (
    UNAVAILABLE,
    Text,
    Upload,
    _count_attempts,
    _reset,
    factors_match,
    read_probes,
    require_biometrics,
)
from app.schemas import MethodsStatus, SessionOut, checked_username
from app.sessions import issue_session

LOGIN_FAILED = "Biometric login failed"
WEBCAM_NEEDS_BOTH = "Webcam sign-in needs both your face and your voice"
NEEDS_AUDIO = "Send an audio recording"
NO_METHOD = "Choose at least one sign-in method"
TAKEN = "Username already taken"

# 503 first (feature off), then the Origin check.
methods_router = APIRouter(
    prefix="/auth", tags=["sign-in methods"], dependencies=[Depends(require_biometrics), Depends(check_origin)]
)
# Registration with any mix of methods: biometrics are only required when a biometric file is sent.
combined_router = APIRouter(prefix="/auth", tags=["sign-in methods"], dependencies=[Depends(check_origin)])


# --- registration ---------------------------------------------------------------------------------


def _username_free(db: Session, username: str) -> None:
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, TAKEN)


def _templates(request: Request, voice_file, video_file, clip_audio=None) -> dict:
    """Validate the samples and return the User columns they produce (nothing is stored yet).

    Voice file only: voice template, voice login. Video only: face + voice from the clip's audio track,
    webcam login. Both: the voice template comes from the voice file and the clip's face is the face
    template; webcam login then compares the clip's own voice against that same template.
    `clip_audio` is the optional separate audio of a webcam-only registration: it feeds the webcam
    method's voice template but does NOT enable voice login.
    """
    if voice_file is None and video_file is None:
        return {}
    if not biometrics_available(request):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE)
    voice, face = read_probes(request, voice_file or clip_audio, video_file)
    if video_file is not None and (voice is None or face is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, WEBCAM_NEEDS_BOTH)
    if voice is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NEEDS_AUDIO)
    cipher = request.app.state.cipher
    columns: dict = {"audio_embedding": cipher.encrypt(voice), "voice_login": voice_file is not None}
    if face is not None:
        columns.update(face_embedding=cipher.encrypt(face), webcam_login=True)
    return columns


def _register(
    request: Request, response: Response, db: Session, username: str, *,
    password: str | None = None, google_token: str | None = None, voice_file=None, video_file=None,
    clip_audio=None,
) -> SessionOut:  # fmt: skip
    """All-or-nothing: every method is validated before the account row exists."""
    throttle, ip = request.app.state.register_throttle, client_ip(request)
    if throttle.is_blocked(ip):
        raise too_many()
    throttle.record(ip)
    try:
        name = checked_username(username)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"username: {exc}") from None
    if not (password or google_token or voice_file is not None or video_file is not None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NO_METHOD)
    _username_free(db, name)
    columns: dict = {"password_hash": NO_PASSWORD}
    if password:
        problem = password_problem(password, name)
        if problem:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
        columns["password_hash"] = hash_password(password)
    if google_token:
        identity = verify_google_or_throttle(request, google_token)
        if db.scalar(select(User.id).where(User.google_sub == identity.sub)) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, GOOGLE_IN_USE)
        email_taken = db.scalar(select(User.id).where(User.email == identity.email)) is not None
        columns.update(google_sub=identity.sub, email=None if email_taken else identity.email)
    columns.update(_templates(request, voice_file, video_file, clip_audio))
    user = User(username=name, **columns)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, TAKEN) from None
    audit.info("register user=%r ip=%s methods=%s", name, ip, sorted(k for k in columns if k != "password_hash"))
    return issue_session(response, user, settings_of(request))


@methods_router.post("/register/voice", status_code=status.HTTP_201_CREATED, response_model=SessionOut)
def register_voice(
    request: Request, response: Response, username: Annotated[str, Form()], audio: Upload = None,
    db: Session = Depends(get_db),
) -> SessionOut:  # fmt: skip
    if audio is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NEEDS_AUDIO)
    return _register(request, response, db, username, voice_file=audio)


@methods_router.post("/register/webcam", status_code=status.HTTP_201_CREATED, response_model=SessionOut)
def register_webcam(
    request: Request, response: Response, username: Annotated[str, Form()], video: Upload = None,
    audio: Upload = None, db: Session = Depends(get_db),
) -> SessionOut:  # fmt: skip
    if video is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, WEBCAM_NEEDS_BOTH)
    return _register(request, response, db, username, video_file=video, clip_audio=audio)


@combined_router.post("/register/combined", status_code=status.HTTP_201_CREATED, response_model=SessionOut)
def register_combined(
    request: Request, response: Response, username: Annotated[str, Form()],
    password: Text = None, google_id_token: Text = None, voice_audio: Upload = None, webcam_video: Upload = None,
    db: Session = Depends(get_db),
) -> SessionOut:  # fmt: skip
    return _register(
        request, response, db, username, password=password, google_token=google_id_token,
        voice_file=voice_audio, video_file=webcam_video,
    )  # fmt: skip


# --- sign-in --------------------------------------------------------------------------------------


def _biometric_login(
    request: Request, response: Response, db: Session, username: str, audio: Upload, video: Upload, *, method: str
) -> SessionOut:  # fmt: skip
    """Voice or webcam sign-in. Strict thresholds; every failure is the same 401."""
    ip, state, name = client_ip(request), request.app.state, username.strip().lower()
    throttles = [state.alone_throttle, state.alone_account_throttle]
    keys = [f"{ip}|{name}", name]
    _count_attempts(throttles, keys, name, ip)
    user = db.scalar(select(User).where(User.username == name))
    required = ("voice",) if method == "voice" else ("voice", "face")
    enabled = user is not None and (user.voice_login if method == "voice" else user.webcam_login)
    if not enabled or not factors_match(request, user, audio, video if method == "webcam" else None, True, required):
        audit.warning("%s login failed user=%r ip=%s", method, name, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, LOGIN_FAILED)
    _reset(throttles, keys)
    audit.info("login ok (%s) user=%r ip=%s", method, name, ip)
    return issue_session(response, user, settings_of(request))


@methods_router.post("/login/voice", response_model=SessionOut)
def login_voice(
    request: Request, response: Response, username: Annotated[str, Form(max_length=64)], audio: Upload = None,
    db: Session = Depends(get_db),
) -> SessionOut:  # fmt: skip
    return _biometric_login(request, response, db, username, audio, None, method="voice")


@methods_router.post("/login/webcam", response_model=SessionOut)
def login_webcam(
    request: Request, response: Response, username: Annotated[str, Form(max_length=64)], video: Upload = None,
    audio: Upload = None, db: Session = Depends(get_db),
) -> SessionOut:  # fmt: skip
    return _biometric_login(request, response, db, username, audio, video, method="webcam")


# --- linking and removal --------------------------------------------------------------------------


def _enroll(request: Request, session: AuthSession, password: str | None, audio: Upload, video: Upload):
    """Re-auth, throttle, then (voice, face) probes."""
    user, throttle = session.user, request.app.state.enroll_throttle
    if throttle.is_blocked(str(user.id)):
        raise too_many()
    require_reauth(request, user, password)
    throttle.record(str(user.id))  # expensive: every call counts
    return read_probes(request, audio, video)


@methods_router.post("/me/voice", response_model=MethodsStatus)
def link_voice(
    request: Request, password: Text = None, audio: Upload = None,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> MethodsStatus:  # fmt: skip
    voice, _ = _enroll(request, session, password, audio, None)
    if voice is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NEEDS_AUDIO)
    user = session.user
    user.audio_embedding = request.app.state.cipher.encrypt(voice)
    user.voice_login = True
    db.commit()
    audit.info("voice sign-in enabled user=%r ip=%s", user.username, client_ip(request))
    return methods_status(user)


@methods_router.post("/me/webcam", response_model=MethodsStatus)
def link_webcam(
    request: Request, password: Text = None, video: Upload = None, audio: Upload = None,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> MethodsStatus:  # fmt: skip
    voice, face = _enroll(request, session, password, audio, video)
    if voice is None or face is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, WEBCAM_NEEDS_BOTH)
    user, cipher = session.user, request.app.state.cipher
    user.audio_embedding, user.face_embedding = cipher.encrypt(voice), cipher.encrypt(face)
    user.webcam_login = True
    db.commit()
    audit.info("webcam sign-in enabled user=%r ip=%s", user.username, client_ip(request))
    return methods_status(user)


def _remove(request: Request, session: AuthSession, db: Session, password: str | None, method: str) -> MethodsStatus:
    user = session.user
    require_reauth(request, user, password)
    if usable_methods(user, without=method) == 0 and (user.voice_login if method == "voice" else user.webcam_login):
        raise HTTPException(status.HTTP_409_CONFLICT, KEEP_ONE)
    if method == "voice":
        user.voice_login = False
        if not user.webcam_login:
            user.audio_embedding = None
    else:
        user.webcam_login = False
        user.face_embedding = None
        if not user.voice_login:
            user.audio_embedding = None
    if not user.has_biometrics:
        user.biometric_2fa = False  # no template left: never keep a factor that cannot be met
    db.commit()
    audit.info("%s sign-in removed user=%r ip=%s", method, user.username, client_ip(request))
    return methods_status(user)


@methods_router.delete("/me/voice", response_model=MethodsStatus)
def remove_voice(
    request: Request, password: Text = None, session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> MethodsStatus:  # fmt: skip
    return _remove(request, session, db, password, "voice")


@methods_router.delete("/me/webcam", response_model=MethodsStatus)
def remove_webcam(
    request: Request, password: Text = None, session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> MethodsStatus:  # fmt: skip
    return _remove(request, session, db, password, "webcam")
