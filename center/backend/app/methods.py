"""Which sign-in methods an account has, and the "keep at least one" rule."""

from datetime import datetime, timezone

from app.models import User
from app.schemas import MethodsStatus, PasskeyOut

KEEP_ONE = "Keep at least one sign-in method"
GOOGLE_IN_USE = "That Google account is already linked to an account"


def has_verified_email(user: User) -> bool:
    return bool(user.email and user.email_verified)


def methods_status(user: User) -> MethodsStatus:
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
    )


def _utc(value: datetime | None) -> datetime | None:
    """SQLite hands timestamps back naive; they are always UTC, so every response says so."""
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


def passkey_items(user: User) -> list[PasskeyOut]:
    return [
        PasskeyOut(
            id=p.id, name=p.name, created_at=_utc(p.created_at), last_used_at=_utc(p.last_used_at),
            backed_up=p.backed_up, transports=[t for t in (p.transports or "").split(",") if t],
        )
        for p in user.passkeys
    ]  # fmt: skip


def methods_lost_on_unlink(user: User) -> tuple[str, ...]:
    """Unlinking Google removes the email too, but only an address Google itself supplied."""
    return ("google", "email") if user.email_from_google else ("google",)


def usable_methods(user: User, without: str | tuple[str, ...] | None = None) -> int:
    """Number of usable sign-in methods, optionally pretending `without` is removed
    ("password", "google", "email", "voice", "webcam" or "passkey"; a tuple removes several).
    An email counts only once verified."""
    removed = (without,) if isinstance(without, str) else tuple(without or ())
    flags = {
        "password": user.has_password,
        "google": user.google_linked,
        "email": has_verified_email(user),
        "voice": user.voice_login,
        "webcam": user.webcam_login,
        "passkey": bool(user.passkeys),
    }
    return sum(1 for name, on in flags.items() if on and name not in removed)
