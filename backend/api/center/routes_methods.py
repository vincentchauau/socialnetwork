"""Voice and webcam sign-in: register with them, sign in with them, link and remove them.

Two independent methods, each with its own template: voice = audio template, webcam = face template
only (like a phone Face ID: the sound of a webcam clip is never used).

Re-auth rule: linking/removing asks for the password only when the account HAS one. Accounts without
a password (voice, webcam or Google only) have nothing to re-enter, so no re-auth is asked for them:
a stolen session of such an account can change its methods (known limitation).
"""

import secrets
from typing import Annotated, Callable

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.center.audit import audit
from api.center.db import get_db
from api.center.handles import key_of, unique_handle
from api.center.identify import (
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
from api.center.throttle import pair_key
from api.center.deps import AuthSession, biometrics_available, check_origin, client_ip, csrf_session, ensure_reauth, settings_of, too_many
from api.center import emailtokens as et
from api.center import usernames
from api.center.liveness import liveness_ok
from api.center.methods import GOOGLE_IN_USE, KEEP_ONE, methods_status, usable_methods
from api.center.models import User
from api.center.notify import notify, send_link_mail
from api.center.passwords import NO_PASSWORD, hash_password, password_problem
from api.center.routes_auth import verify_google_or_throttle
from api.center.routes_passkeys import verified_signup_passkey
from api.center.routes_biometrics import (
    UNAVAILABLE,
    Text,
    Upload,
    count_attempts,
    _reset,
    factors_match,
    read_face,
    read_probes,
    ensure_biometrics,
)
from api.center.schemas import MethodsStatus, MfaRequired, SessionOut, checked_username, normalized_email
from api.center.sessions import begin_session, finish_primary_biometric_login

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
router = APIRouter(
    prefix="/auth", tags=["sign-in methods"], dependencies=[Depends(ensure_biometrics), Depends(check_origin)]
)
# Registration with any mix of methods: biometrics are only required when a biometric file is sent.
combined_router = APIRouter(prefix="/auth", tags=["sign-in methods"], dependencies=[Depends(check_origin)])


# --- registration ---------------------------------------------------------------------------------


def username_free(db: Session, username: str) -> None:
    if usernames.unavailable(db, username):
        raise HTTPException(status.HTTP_409_CONFLICT, TAKEN)


def handle_taken(db: Session, handle: str) -> bool:
    return usernames.unavailable(db, handle)


def random_handle(db: Session) -> str:
    """`user-` + 6 hex chars (no email involved); retried on collision."""
    while True:
        handle = GENERATED_PREFIX + secrets.token_hex(GENERATED_HEX_CHARS // 2)
        if not handle_taken(db, handle):
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


def signup_address(email: str | None) -> str | None:
    """The optional sign-up email, normalised; email alone is never a method, so no extra rule here."""
    if email is None or not email.strip():
        return None
    try:
        return normalized_email(email)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"email: {exc}") from None


def send_signup_verification(
    request: Request, background: BackgroundTasks, db: Session, user: User, address: str
) -> None:
    """Best effort: the account exists already, so nothing here may fail the registration.

    Capped per target address (a sign-up must not become a way to mail someone repeatedly), and skipped
    when the address is verified on another account.
    """
    state = request.app.state
    if not settings_of(request).email_enabled:
        return
    try:
        if not state.register_mail_throttle.check_and_record(address):
            return
        if db.scalar(select(User.id).where(User.email == address, User.email_verified.is_(True))) is not None:
            return
        issued = et.issue(db, user, et.VERIFY, address, with_code=True)
        send_link_mail(request, background, et.VERIFY, address, issued.token, issued.code)
    except Exception as exc:  # noqa: BLE001 - never fail a registration over a mail
        db.rollback()
        audit.warning("signup verification mail not queued error=%s", type(exc).__name__)


def register_method(password, google_token, passkey, voice_file, video_file) -> str:
    """The primary factor of a sign-up, for the session list (first of: password, Google, passkey, voice, webcam)."""
    if password:
        return "password"
    if google_token:
        return "google"
    if passkey:
        return "passkey"
    return "voice" if voice_file is not None else "webcam"


def _register(
    request: Request, response: Response, db: Session, username: str | None, *,
    password: str | None = None, google_token: str | None = None, voice_file=None, video_file=None,
    passkey: tuple[str, str] | None = None, email: str | None = None, background: BackgroundTasks | None = None,
) -> SessionOut:  # fmt: skip
    """All-or-nothing: every method is validated before the account row exists."""
    throttle, ip = request.app.state.register_throttle, client_ip(request)
    if not throttle.check_and_record(ip):
        raise too_many()
    if not (password or google_token or voice_file is not None or video_file is not None or passkey):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NO_METHOD)
    # Google, voice, webcam and passkey sign in without a name, so only a password needs one. A generated
    # handle can be renamed later (POST /auth/me/username).
    address = signup_address(email)  # validated before anything is stored
    generate = username is None or not username.strip()
    if generate and password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, CHOOSE_USERNAME)
    name = ""
    if not generate:
        try:
            name = checked_username(username)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"username: {exc}") from None
        username_free(db, name)
    columns: dict = {"password_hash": NO_PASSWORD}
    if password:
        problem = password_problem(password)
        if problem:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
        columns["password_hash"] = hash_password(password)
    if google_token:
        identity = verify_google_or_throttle(request, google_token)
        if db.scalar(select(User.id).where(User.google_sub == identity.sub)) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, GOOGLE_IN_USE)
        email_taken = db.scalar(select(User.id).where(User.email == identity.email)) is not None
        columns.update(
            google_sub=identity.sub, email=None if email_taken else identity.email,
            email_from_google=not email_taken,
        )  # fmt: skip
        if generate:
            name = unique_handle(identity.email, lambda h: handle_taken(db, h))
    columns.update(_templates(request, db, voice_file, video_file))
    if generate and not name:
        name = random_handle(db)
    user = User(username=name, **columns)
    if passkey:  # verified last (it burns its challenge), still before anything is stored
        user.passkeys.append(verified_signup_passkey(request, db, *passkey))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, TAKEN) from None
    if address and background is not None:
        send_signup_verification(request, background, db, user, address)
    audit.info("register user=%r ip=%s methods=%s", name, ip,
               sorted([k for k in columns if k != "password_hash"] + (["passkey"] if passkey else [])))
    return begin_session(response, request, db, user, settings_of(request), register_method(
        password, google_token, passkey, voice_file, video_file
    ))


@router.post("/register/voice", status_code=status.HTTP_201_CREATED, response_model=SessionOut)
def register_voice(
    request: Request, response: Response, username: Annotated[str | None, Form()] = None, audio: Upload = None,
    db: Session = Depends(get_db),
) -> SessionOut:  # fmt: skip
    if audio is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NEEDS_AUDIO)
    return _register(request, response, db, username, voice_file=audio)


@router.post("/register/webcam", status_code=status.HTTP_201_CREATED, response_model=SessionOut)
def register_webcam(
    request: Request, response: Response, username: Annotated[str, Form()], video: Upload = None,
    liveness_token: Text = None, db: Session = Depends(get_db),
) -> SessionOut:  # fmt: skip
    if video is None or not liveness_ok(request, liveness_token, video):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NEEDS_FACE)  # an `audio` field is ignored
    return _register(request, response, db, username, video_file=video)


@combined_router.post("/register/combined", status_code=status.HTTP_201_CREATED, response_model=SessionOut)
def register_combined(
    request: Request, response: Response, username: Annotated[str | None, Form()] = None,
    password: Text = None, google_id_token: Text = None, voice_audio: Upload = None, webcam_video: Upload = None,
    passkey_credential: Text = None, passkey_challenge_token: Text = None, email: Text = None,
    background: BackgroundTasks = None, liveness_token: Text = None, db: Session = Depends(get_db),
) -> SessionOut:  # fmt: skip
    if webcam_video is not None and not liveness_ok(request, liveness_token, webcam_video):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NEEDS_FACE)
    if bool(passkey_credential) != bool(passkey_challenge_token):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, PASSKEY_BOTH)
    passkey = (passkey_credential, passkey_challenge_token) if passkey_credential and passkey_challenge_token else None
    return _register(
        request, response, db, username, password=password, google_token=google_id_token,
        voice_file=voice_audio, video_file=webcam_video, passkey=passkey, email=email, background=background,
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
    request: Request, response: Response, db: Session, username: str, audio: Upload, video: Upload, *, method: str,
    live: Callable[[], bool] = lambda: True,
) -> SessionOut | MfaRequired:  # fmt: skip
    """Voice (audio only) or webcam (face only) sign-in. Strict thresholds; every failure is the same 401."""
    ip, state, name = client_ip(request), request.app.state, key_of(username)
    throttles = [state.alone_throttle, state.alone_account_throttle]
    keys = [pair_key(ip, name), name]
    count_attempts(throttles, keys, name, ip)
    live_ok = live() if method == "webcam" else True  # after the lockout check: a locked key costs no analysis
    user = db.scalar(select(User).where(func.lower(User.username) == name))
    if user is None:
        matched = False
    elif method == "voice":
        matched = user.voice_login and factors_match(request, user, audio, None, True, ("voice",))
    else:
        matched = user.webcam_login and live_ok and _face_matches(request, user, video)
    if not matched:
        audit.warning("%s login failed user=%r ip=%s", method, name, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, LOGIN_FAILED)
    _reset(throttles, keys)
    audit.info("login ok (%s) user=%r ip=%s", method, name, ip)
    return finish_primary_biometric_login(
        response, user, settings_of(request), request=request, db=db, method=method
    )


def identify_login(
    request: Request, response: Response, db: Session, upload: Upload, *, method: str,
    live: Callable[[], bool] = lambda: True,
) -> SessionOut | MfaRequired:  # fmt: skip
    """Sign-in without a username (1-N), by face (webcam) or voice alone. Every failure is the same 401
    and the same work. Face and voice use separate throttle counters.

    Audit lines carry the outcome and address only: never vectors, never a guessed name.
    """
    ip, state = client_ip(request), request.app.state
    if method == "voice":
        ip_throttle, global_throttle = state.voice_identify_ip_throttle, state.voice_identify_global_throttle
        kind, find, read = VOICE, identify_voice, voice_or_none
    else:
        ip_throttle, global_throttle = state.identify_ip_throttle, state.identify_global_throttle
        kind, find, read = FACE, identify, face_or_none
    if ip_throttle.is_blocked(ip) or global_throttle.is_blocked(IDENTIFY_GLOBAL_KEY):
        audit.warning("%s identify locked ip=%s", method, ip)
        raise too_many()
    ip_throttle.record(ip)  # counted up front (O(N) work); the address key is cleared on success
    global_throttle.record(IDENTIFY_GLOBAL_KEY)
    if too_many_candidates(db, kind):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, ENTER_USERNAME)
    live_ok = live() if method == "webcam" else True  # after the throttle check and count
    probe = read(request, upload)
    user = find(request, db, probe) if probe is not None and live_ok else None
    if user is None:
        audit.warning("%s identify failed ip=%s", method, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, LOGIN_FAILED)
    ip_throttle.reset(ip)
    audit.info("login ok (%s identify) user=%r ip=%s", method, user.username, ip)
    return finish_primary_biometric_login(
        response, user, settings_of(request), request=request, db=db, method=method
    )


def face_or_none(request: Request, video: Upload) -> bytes | None:
    """The clip face, or None (an unusable clip depends on no account)."""
    try:
        return read_face(request, video)
    except HTTPException:
        return None


def voice_or_none(request: Request, audio: Upload) -> bytes | None:
    """The voice embedding, or None (an unusable recording depends on no account)."""
    try:
        return read_probes(request, audio, None)[0]
    except HTTPException:
        return None


@router.post("/login/voice", response_model=SessionOut | MfaRequired)
def login_voice(
    request: Request, response: Response, username: Annotated[str | None, Form(max_length=64)] = None,
    audio: Upload = None, db: Session = Depends(get_db),
) -> SessionOut | MfaRequired:  # fmt: skip
    """With a username: 1-1 comparison. Without: 1-N identification by voice alone."""
    if username is None or not username.strip():
        return identify_login(request, response, db, audio, method="voice")
    return _biometric_login(request, response, db, username, audio, None, method="voice")


@router.post("/login/webcam", response_model=SessionOut | MfaRequired)
def login_webcam(
    request: Request, response: Response, username: Annotated[str | None, Form(max_length=64)] = None,
    video: Upload = None, liveness_token: Text = None, db: Session = Depends(get_db),
) -> SessionOut | MfaRequired:  # fmt: skip
    """Face only: an `audio` field, if sent, is ignored. `liveness_token`: see app.liveness."""
    live = lambda: liveness_ok(request, liveness_token, video)  # noqa: E731 - run after the throttles
    if username is None or not username.strip():
        return identify_login(request, response, db, video, method="webcam", live=live)
    return _biometric_login(request, response, db, username, None, video, method="webcam", live=live)


# --- linking and removal --------------------------------------------------------------------------


def _enroll(request: Request, session: AuthSession, password: str | None) -> None:
    """Throttle and re-auth, before any (expensive) sample processing."""
    user, throttle = session.user, request.app.state.enroll_throttle
    if throttle.is_blocked(str(user.id)):
        raise too_many()
    ensure_reauth(request, user, password)
    throttle.record(str(user.id))  # expensive: every call counts


@router.post("/me/voice", response_model=MethodsStatus)
def link_voice(
    request: Request, background: BackgroundTasks, password: Text = None, audio: Upload = None,
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
    notify(request, background, user, "voice_added")
    return methods_status(user)


@router.post("/me/webcam", response_model=MethodsStatus)
def link_webcam(
    request: Request, background: BackgroundTasks, password: Text = None, video: Upload = None,
    liveness_token: Text = None, session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> MethodsStatus:  # fmt: skip
    """Face template only; the voice template (if any) is never touched. An `audio` field is ignored."""
    _enroll(request, session, password)
    if not liveness_ok(request, liveness_token, video):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NEEDS_FACE)
    face = read_face(request, video)
    if face is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, NEEDS_FACE)
    user = session.user
    ensure_face_unique(request, db, face, exclude_user_id=user.id)  # own old face is excluded
    user.face_embedding = request.app.state.cipher.encrypt(face)
    user.webcam_login = True
    db.commit()
    audit.info("webcam sign-in enabled user=%r ip=%s", user.username, client_ip(request))
    notify(request, background, user, "webcam_added")
    return methods_status(user)


def _remove(
    request: Request, background: BackgroundTasks, session: AuthSession, db: Session, password: str | None, method: str
) -> MethodsStatus:
    user = session.user
    ensure_reauth(request, user, password)
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
    notify(request, background, user, f"{method}_removed")
    return methods_status(user)


@router.delete("/me/voice", response_model=MethodsStatus)
def remove_voice(
    request: Request, background: BackgroundTasks, password: Text = None, session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> MethodsStatus:  # fmt: skip
    return _remove(request, background, session, db, password, "voice")


@router.delete("/me/webcam", response_model=MethodsStatus)
def remove_webcam(
    request: Request, background: BackgroundTasks, password: Text = None, session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> MethodsStatus:  # fmt: skip
    return _remove(request, background, session, db, password, "webcam")
