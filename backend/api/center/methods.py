"""Which sign-in methods an account has, and the "keep at least one" rule."""

from datetime import datetime, timezone

from api.center.models import User
from api.center.phonenum import mask_phone
from api.center.schemas import MethodsStatus, PasskeyOut

import logging
logger = logging.getLogger(__name__)

KEEP_ONE = "Keep at least one sign-in method"
PASSKEY_LIMIT = "Passkey limit reached"
MAX_PASSKEYS_PER_ACCOUNT = 10
GOOGLE_IN_USE = "That Google account is already linked to an account"


def has_verified_email(user: User) -> bool:
    try:
        return bool(user.email and user.email_verified)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("has_verified_email failed")
        raise


def methods_status(user: User) -> MethodsStatus:
    try:
        return MethodsStatus(
            has_password=user.has_password,
            google_linked=user.google_linked,
            voice_login=user.voice_login,
            webcam_login=user.webcam_login,
            has_audio=bool(user.audio_embedding),
            has_face=bool(user.face_embedding),
            require_biometric_2fa=user.biometric_2fa,
            passkey_count=len(user.passkeys),
            email_verified=has_verified_email(user),
            phone=mask_phone(user.phone) if user.phone and user.phone_verified else None,
            phone_verified=bool(user.phone and user.phone_verified),
            totp_enabled=user.totp_enabled,
            recovery_codes_left=sum(1 for c in user.recovery_codes if c.used_at is None),
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("methods_status failed")
        raise


def utc_methods(value: datetime | None) -> datetime | None:
    """SQLite hands timestamps back naive; they are always UTC, so every response says so."""
    try:
        return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("utc_methods failed")
        raise


def passkey_items(user: User) -> list[PasskeyOut]:
    try:
        return [
            PasskeyOut(
                id=p.id, name=p.name, created_at=utc_methods(p.created_at), last_used_at=utc_methods(p.last_used_at),
                backed_up=p.backed_up, transports=[t for t in (p.transports or "").split(",") if t],
            )
            for p in user.passkeys
        ]  # fmt: skip
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("passkey_items failed")
        raise


def methods_lost_on_unlink(user: User) -> tuple[str, ...]:
    """Unlinking Google removes the email too, but only an address Google itself supplied."""
    try:
        return ("google", "email") if user.email_from_google else ("google",)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("methods_lost_on_unlink failed")
        raise


def usable_methods(user: User, without: str | tuple[str, ...] | None = None) -> int:
    """Number of usable sign-in methods, optionally pretending `without` is removed
    ("password", "google", "email", "voice", "webcam" or "passkey"; a tuple removes several).
    An email counts only once verified."""
    try:
        removed = (without,) if isinstance(without, str) else tuple(without or ())
        flags = {
            "password": user.has_password,
            "google": user.google_linked,
            "email": has_verified_email(user),
            "phone": bool(user.phone and user.phone_verified),
            "voice": user.voice_login,
            "webcam": user.webcam_login,
            "passkey": bool(user.passkeys),
        }
        return sum(1 for name, on in flags.items() if on and name not in removed)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("usable_methods failed")
        raise
