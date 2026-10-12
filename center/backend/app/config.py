"""Settings read from the environment; unsafe production configuration refuses to start."""

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from sn_shared.security import MIN_SECRET_LENGTH

DEFAULT_ORIGINS = ("http://localhost:8080",)


class ConfigError(RuntimeError):
    """A required setting is missing or unsafe."""


def _flag(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in ("1", "true", "yes")


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from None
    if value <= 0:
        raise ConfigError(f"{name} must be greater than 0")
    return value


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from None


@dataclass(frozen=True)
class Settings:
    jwt_secret: str
    env: str = "development"
    cookie_secure: bool = False
    access_minutes: int = 60
    refresh_days: int = 14
    allowed_origins: tuple[str, ...] = DEFAULT_ORIGINS
    google_client_id: str = ""
    biometrics_enabled: bool = False
    data_key: str = ""
    audio_threshold: float = 0.8  # minimum cosine similarity of voices
    face_threshold: float = 0.6  # maximum distance between faces
    audio_threshold_alone: float = 0.88  # stricter when biometrics are the only factor
    face_threshold_alone: float = 0.45
    face_identify_margin: float = 0.08  # 1-N sign-in: best face must beat the runner-up by this distance
    voice_identify_margin: float = 0.05  # 1-N voice sign-in: best similarity must beat the runner-up by this
    ffmpeg_timeout: int = 20
    max_frames: int = 30
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "Mạng xã hội"

    @property
    def production(self) -> bool:
        return self.env == "production"

    @property
    def webauthn_origins(self) -> tuple[str, ...]:
        return self.allowed_origins

    @staticmethod
    def from_env() -> "Settings":
        secret = os.environ.get("JWT_SECRET", "")
        if len(secret) < MIN_SECRET_LENGTH:
            raise ConfigError(f"JWT_SECRET must be set and at least {MIN_SECRET_LENGTH} characters long")
        env = os.environ.get("APP_ENV", "development").strip().lower() or "development"
        if env not in ("development", "production"):
            raise ConfigError("APP_ENV must be 'development' or 'production'")
        origins = tuple(o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip())
        rp_id = os.environ.get("WEBAUTHN_RP_ID", "").strip().lower()
        if not rp_id and env != "production":  # production must name its RP ID explicitly
            rp_id = urlparse((origins or DEFAULT_ORIGINS)[0]).hostname or "localhost"
        settings = Settings(
            jwt_secret=secret,
            env=env,
            cookie_secure=os.environ.get("COOKIE_SECURE") == "1",
            access_minutes=_positive_int("ACCESS_TOKEN_MINUTES", 60),
            refresh_days=_positive_int("REFRESH_DAYS", 14),
            allowed_origins=origins or DEFAULT_ORIGINS,
            google_client_id=os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
            biometrics_enabled=_flag("BIOMETRICS_ENABLED"),
            data_key=os.environ.get("DATA_KEY", "").strip(),
            audio_threshold=_float("AUDIO_THRESHOLD", 0.8),
            face_threshold=_float("FACE_THRESHOLD", 0.6),
            audio_threshold_alone=_float("AUDIO_THRESHOLD_ALONE", 0.88),
            face_threshold_alone=_float("FACE_THRESHOLD_ALONE", 0.45),
            face_identify_margin=_float("FACE_IDENTIFY_MARGIN", 0.08),
            voice_identify_margin=_float("VOICE_IDENTIFY_MARGIN", 0.05),
            webauthn_rp_id=rp_id,
            webauthn_rp_name=os.environ.get("WEBAUTHN_RP_NAME", "").strip() or "Mạng xã hội",
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.production and not self.cookie_secure:
            raise ConfigError("Production requires COOKIE_SECURE=1")
        if self.production and not self.webauthn_rp_id:
            raise ConfigError("Production requires WEBAUTHN_RP_ID (the domain passkeys are bound to)")
        if self.biometrics_enabled and not self.data_key:
            raise ConfigError("BIOMETRICS_ENABLED=1 requires DATA_KEY (a Fernet key)")
