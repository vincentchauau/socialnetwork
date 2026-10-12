"""Which sign-in methods an account has, and the "keep at least one" rule."""

from app.models import User
from app.schemas import MethodsStatus

KEEP_ONE = "Keep at least one sign-in method"
GOOGLE_IN_USE = "That Google account is already linked to an account"


def methods_status(user: User) -> MethodsStatus:
    return MethodsStatus(
        has_password=user.has_password,
        google_linked=user.google_linked,
        voice_login=user.voice_login,
        webcam_login=user.webcam_login,
        has_audio=bool(user.audio_embedding),
        has_face=bool(user.face_embedding),
        require_biometric_2fa=user.biometric_2fa,
    )


def usable_methods(user: User, without: str | None = None) -> int:
    """Number of usable sign-in methods, optionally pretending `without` is removed
    ("password", "google", "voice" or "webcam")."""
    flags = {
        "password": user.has_password,
        "google": user.google_linked,
        "voice": user.voice_login,
        "webcam": user.webcam_login,
    }
    return sum(1 for name, on in flags.items() if on and name != without)
