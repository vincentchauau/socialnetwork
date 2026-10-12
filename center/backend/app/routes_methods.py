"""Voice and webcam sign-in: register with them, sign in with them, link and remove them.

Two independent methods, each with its own template: voice = audio template, webcam = face template
only (like a phone Face ID: the sound of a webcam clip is never used).

Re-auth rule: linking/removing asks for the password only when the account HAS one. Accounts without
a password (voice, webcam or Google only) have nothing to re-enter, so no re-auth is asked for them:
a stolen session of such an account can change its methods (known limitation).
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_db
from app.handles import unique_handle
from app.identify import (
    ENTER_USERNAME,
    IDENTIFY_GLOBAL_KEY,
    FACE,
    VOICE,
    ensure_face_unique,
    ensure_voice_unique,
    identify,
    identify_voice,
    too_many_candidates,
)
from app.deps import AuthSession, biometrics_available, check_origin, client_ip, csrf_session, require_reauth, settings_of, too_many
from app.methods import GOOGLE_IN_USE, KEEP_ONE, methods_status, usable_methods
from app.models import User
from app.passwords import NO_PASSWORD, hash_password, password_problem
from app.routes_auth import verify_google_or_throttle
from app.routes_passkeys import verified_signup_passkey
from app.routes_biometrics import (
    UNAVAILABLE,
    Text,
    Upload,
    _count_attempts,
    _reset,
    factors_match,
    read_face,
    read_probes,
    require_biometrics,
)
from app.schemas import MethodsStatus, SessionOut, checked_username
from app.sessions import issue_session

LOGIN_FAILED = "Biometric login failed"
NEEDS_FACE = "Send a video with your face"
NEEDS_AUDIO = "Send an audio recording"
NO_METHOD = "Choose at least one sign-in method"
TAKEN = "Username already taken"
CHOOSE_USERNAME = "Choose a username"
PASSKEY_BOTH = "Send both passkey_credential and passkey_challenge_token"
GENERATED_PREFIX = "user-"
GENERATED_HEX_CHARS = 6

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


def _handle_taken(db: Session, handle: str) -> bool:
    return db.scalar(select(User.id).where(User.username == handle)) is not None


def _random_handle(db: Session) -> str:
    """`user-` + 6 hex chars (no email involved); retried on collision."""
    while True:
        handle = GENERATED_PREFIX + secrets.token_hex(GENERATED_HEX_CHARS // 2)
        if not _handle_taken(db, handle):
            return handle


def _templates(
    request: Request, db: Session, voice_file, video_file, exclude_user_id: int | None = None
) -> dict:
    """Validate the samples and return the User columns they produce (nothing is stored yet).

    Voice file: voice template + voice login. Webcam clip: face template + webcam login, from the face
    ONLY (the clip's sound is ignored). Both: two independent templates.
    """
    if voice_file is None and video_file is None:
        return {}
    if not biometrics_available(request):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE)
    voice = read_probes(request, voice_file, None)[0] if voice_file is not None else None
    face = read_face(request, video_file) if video_file is not None else None
    if voice_file is not None and voice is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NEEDS_AUDIO)
    if video_file is not None and face is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NEEDS_FACE)
    cipher = request.app.state.cipher
    columns: dict = {}
    if voice is not None:
        ensure_voice_unique(request, db, voice, exclude_user_id)
        columns.update(audio_embedding=cipher.encrypt(voice), voice_login=True)
    if face is not None:
        ensure_face_unique(request, db, face, exclude_user_id)
        columns.update(face_embedding=cipher.encrypt(face), webcam_login=True)
    return columns


def _register(
    request: Request, response: Response, db: Session, username: str | None, *,
    password: str | None = None, google_token: str | None = None, voice_file=None, video_file=None,
    passkey: tuple[str, str] | None = None,
) -> SessionOut:  # fmt: skip
    """All-or-nothing: every method is validated before the account row exists."""
    throttle, ip = request.app.state.register_throttle, client_ip(request)
    if throttle.is_blocked(ip):
        raise too_many()
    throttle.record(ip)
    if not (password or google_token or voice_file is not None or video_file is not None or passkey):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NO_METHOD)
    # Google, voice, webcam and passkey sign in without a name, so only a password needs one. There is NO rename
    # endpoint (usernames are denormalised in other services), hence the generated handle is permanent.
    generate = username is None or not username.strip()
    if generate and password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, CHOOSE_USERNAME)
    name = ""
    if not generate:
        try:
            name = checked_username(username)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"username: {exc}") from None
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
        if generate:
            name = unique_handle(identity.email, lambda h: _handle_taken(db, h))
    columns.update(_templates(request, db, voice_file, video_file))
    if generate and not name:
        name = _random_handle(db)
    user = User(username=name, **columns)
    if passkey:  # verified last (it burns its challenge), still before anything is stored
        user.passkeys.append(verified_signup_passkey(request, db, *passkey))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, TAKEN) from None
    audit.info("register user=%r ip=%s methods=%s", name, ip,
               sorted([k for k in columns if k != "password_hash"] + (["passkey"] if passkey else [])))
    return issue_session(response, user, settings_of(request))


@methods_router.post("/register/voice", status_code=status.HTTP_201_CREATED, response_model=SessionOut)
def register_voice(
    request: Request, response: Response, username: Annotated[str | None, Form()] = None, audio: Upload = None,
    db: Session = Depends(get_db),
) -> SessionOut:  # fmt: skip
    if audio is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NEEDS_AUDIO)
    return _register(request, response, db, username, voice_file=audio)


@methods_router.post("/register/webcam", status_code=status.HTTP_201_CREATED, response_model=SessionOut)
def register_webcam(
    request: Request, response: Response, username: Annotated[str, Form()], video: Upload = None,
    db: Session = Depends(get_db),
) -> SessionOut:  # fmt: skip
    if video is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NEEDS_FACE)  # an `audio` field is ignored
    return _register(request, response, db, username, video_file=video)


@combined_router.post("/register/combined", status_code=status.HTTP_201_CREATED, response_model=SessionOut)
def register_combined(
    request: Request, response: Response, username: Annotated[str | None, Form()] = None,
    password: Text = None, google_id_token: Text = None, voice_audio: Upload = None, webcam_video: Upload = None,
    passkey_credential: Text = None, passkey_challenge_token: Text = None, db: Session = Depends(get_db),
) -> SessionOut:  # fmt: skip
    if bool(passkey_credential) != bool(passkey_challenge_token):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, PASSKEY_BOTH)
    passkey = (passkey_credential, passkey_challenge_token) if passkey_credential and passkey_challenge_token else None
    return _register(
        request, response, db, username, password=password, google_token=google_id_token,
        voice_file=voice_audio, video_file=webcam_video, passkey=passkey,
    )  # fmt: skip


# --- sign-in --------------------------------------------------------------------------------------


def _face_matches(request: Request, user: User, video: Upload) -> bool:
    """Strict 1-1 face comparison; any processing error is a plain failure."""
    try:
        face = read_face(request, video)
    except HTTPException as exc:
        audit.warning("webcam login error user=%r status=%s", user.username, exc.status_code)
        return False
    template = request.app.state.cipher.decrypt(user.face_embedding) if user.face_embedding else None
    return face is not None and template is not None and request.app.state.biometrics.face_matches(template, face, True)


def _biometric_login(
    request: Request, response: Response, db: Session, username: str, audio: Upload, video: Upload, *, method: str
) -> SessionOut:  # fmt: skip
    """Voice (audio only) or webcam (face only) sign-in. Strict thresholds; every failure is the same 401."""
    ip, state, name = client_ip(request), request.app.state, username.strip().lower()
    throttles = [state.alone_throttle, state.alone_account_throttle]
    keys = [f"{ip}|{name}", name]
    _count_attempts(throttles, keys, name, ip)
    user = db.scalar(select(User).where(User.username == name))
    if user is None:
        matched = False
    elif method == "voice":
        matched = user.voice_login and factors_match(request, user, audio, None, True, ("voice",))
    else:
        matched = user.webcam_login and _face_matches(request, user, video)
    if not matched:
        audit.warning("%s login failed user=%r ip=%s", method, name, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, LOGIN_FAILED)
    _reset(throttles, keys)
    audit.info("login ok (%s) user=%r ip=%s", method, name, ip)
    return issue_session(response, user, settings_of(request))


def _identify_login(
    request: Request, response: Response, db: Session, upload: Upload, *, method: str
) -> SessionOut:  # fmt: skip
    """Sign-in without a username (1-N), by face (webcam) or voice alone. Every failure is the same 401
    and the same work. Face and voice use separate throttle counters.

    Audit lines carry the outcome and address only: never vectors, never a guessed name.
    """
    ip, state = client_ip(request), request.app.state
    if method == "voice":
        ip_throttle, global_throttle = state.voice_identify_ip_throttle, state.voice_identify_global_throttle
        kind, find, read = VOICE, identify_voice, _voice_or_none
    else:
        ip_throttle, global_throttle = state.identify_ip_throttle, state.identify_global_throttle
        kind, find, read = FACE, identify, _face_or_none
    if ip_throttle.is_blocked(ip) or global_throttle.is_blocked(IDENTIFY_GLOBAL_KEY):
        audit.warning("%s identify locked ip=%s", method, ip)
        raise too_many()
    ip_throttle.record(ip)  # counted up front (O(N) work); the address key is cleared on success
    global_throttle.record(IDENTIFY_GLOBAL_KEY)
    if too_many_candidates(db, kind):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, ENTER_USERNAME)
    probe = read(request, upload)
    user = find(request, db, probe) if probe is not None else None
    if user is None:
        audit.warning("%s identify failed ip=%s", method, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, LOGIN_FAILED)
    ip_throttle.reset(ip)
    audit.info("login ok (%s identify) user=%r ip=%s", method, user.username, ip)
    return issue_session(response, user, settings_of(request))


def _face_or_none(request: Request, video: Upload) -> bytes | None:
    """The clip face, or None (an unusable clip depends on no account)."""
    try:
        return read_face(request, video)
    except HTTPException:
        return None


def _voice_or_none(request: Request, audio: Upload) -> bytes | None:
    """The voice embedding, or None (an unusable recording depends on no account)."""
    try:
        return read_probes(request, audio, None)[0]
    except HTTPException:
        return None


@methods_router.post("/login/voice", response_model=SessionOut)
def login_voice(
    request: Request, response: Response, username: Annotated[str | None, Form(max_length=64)] = None,
    audio: Upload = None, db: Session = Depends(get_db),
) -> SessionOut:  # fmt: skip
    """With a username: 1-1 comparison. Without: 1-N identification by voice alone."""
    if username is None or not username.strip():
        return _identify_login(request, response, db, audio, method="voice")
    return _biometric_login(request, response, db, username, audio, None, method="voice")


@methods_router.post("/login/webcam", response_model=SessionOut)
def login_webcam(
    request: Request, response: Response, username: Annotated[str | None, Form(max_length=64)] = None,
    video: Upload = None, db: Session = Depends(get_db),
) -> SessionOut:  # fmt: skip
    """Face only: an `audio` field, if sent, is ignored."""
    if username is None or not username.strip():
        return _identify_login(request, response, db, video, method="webcam")
    return _biometric_login(request, response, db, username, None, video, method="webcam")


# --- linking and removal --------------------------------------------------------------------------


def _enroll(request: Request, session: AuthSession, password: str | None) -> None:
    """Throttle and re-auth, before any (expensive) sample processing."""
    user, throttle = session.user, request.app.state.enroll_throttle
    if throttle.is_blocked(str(user.id)):
        raise too_many()
    require_reauth(request, user, password)
    throttle.record(str(user.id))  # expensive: every call counts


@methods_router.post("/me/voice", response_model=MethodsStatus)
def link_voice(
    request: Request, password: Text = None, audio: Upload = None,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> MethodsStatus:  # fmt: skip
    _enroll(request, session, password)
    voice, _ = read_probes(request, audio, None)
    if voice is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NEEDS_AUDIO)
    user = session.user
    ensure_voice_unique(request, db, voice, exclude_user_id=user.id)  # own old voice is excluded
    user.audio_embedding = request.app.state.cipher.encrypt(voice)
    user.voice_login = True
    db.commit()
    audit.info("voice sign-in enabled user=%r ip=%s", user.username, client_ip(request))
    return methods_status(user)


@methods_router.post("/me/webcam", response_model=MethodsStatus)
def link_webcam(
    request: Request, password: Text = None, video: Upload = None,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> MethodsStatus:  # fmt: skip
    """Face template only; the voice template (if any) is never touched. An `audio` field is ignored."""
    _enroll(request, session, password)
    face = read_face(request, video)
    if face is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NEEDS_FACE)
    user = session.user
    ensure_face_unique(request, db, face, exclude_user_id=user.id)  # own old face is excluded
    user.face_embedding = request.app.state.cipher.encrypt(face)
    user.webcam_login = True
    db.commit()
    audit.info("webcam sign-in enabled user=%r ip=%s", user.username, client_ip(request))
    return methods_status(user)


def _remove(request: Request, session: AuthSession, db: Session, password: str | None, method: str) -> MethodsStatus:
    user = session.user
    require_reauth(request, user, password)
    if usable_methods(user, without=method) == 0 and (user.voice_login if method == "voice" else user.webcam_login):
        raise HTTPException(status.HTTP_409_CONFLICT, KEEP_ONE)
    if method == "voice":  # each method owns its template: voice = audio, webcam = face
        user.voice_login = False
        user.audio_embedding = None
    else:
        user.webcam_login = False
        user.face_embedding = None
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
