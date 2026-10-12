"""Settings read from the environment; unsafe production configuration refuses to start."""

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from app.audit import audit
from sn_shared.security import MIN_SECRET_LENGTH

DEFAULT_ORIGINS = ("http://localhost:8080",)
LOCAL_SMTP_HOSTS = ("localhost", "127.0.0.1", "::1", "mailpit")  # dev hosts where plaintext auth stays on the machine
SMTP_SSL_PORT = 465


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


def _flag_default_on(name: str) -> bool:
    return os.environ.get(name, "1").strip().lower() in ("1", "true", "yes")


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
    smtp_host: str = ""  # email features are enabled iff this is set
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Mạng xã hội <no-reply@localhost>"
    smtp_starttls: bool = True
    smtp_ssl: bool = False  # implicit TLS (port 465, smtplib.SMTP_SSL)
    smtp_allow_plaintext_auth: bool = False  # let SMTP_USER log in without TLS to a non-local host
    public_url: str = "http://localhost:8080"  # base of every link in a mail; never taken from a request

    @property
    def smtp_plaintext_auth_refused(self) -> bool:
        """Credentials would cross the network unencrypted: refused unless explicitly allowed or the host is local."""
        return bool(
            self.smtp_host and self.smtp_user and not self.smtp_ssl and not self.smtp_starttls
            and not self.smtp_allow_plaintext_auth and self.smtp_host.strip().lower() not in LOCAL_SMTP_HOSTS
        )  # fmt: skip

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host) and not self.smtp_plaintext_auth_refused

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
        public_url = os.environ.get("PUBLIC_URL", "").strip().rstrip("/") or (origins or DEFAULT_ORIGINS)[0]
        if urlparse(public_url).scheme not in ("http", "https") or not urlparse(public_url).netloc:
            raise ConfigError("PUBLIC_URL must be an http(s) URL")
        smtp_ssl = _flag("SMTP_SSL")
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
            smtp_host=os.environ.get("SMTP_HOST", "").strip(),
            smtp_port=_positive_int("SMTP_PORT", SMTP_SSL_PORT if smtp_ssl else 587),
            smtp_user=os.environ.get("SMTP_USER", "").strip(),
            smtp_password=os.environ.get("SMTP_PASSWORD", ""),
            smtp_from=os.environ.get("SMTP_FROM", "").strip() or "Mạng xã hội <no-reply@localhost>",
            smtp_starttls=_flag_default_on("SMTP_STARTTLS"),
            smtp_ssl=smtp_ssl,
            smtp_allow_plaintext_auth=_flag("SMTP_ALLOW_PLAINTEXT_AUTH"),
            public_url=public_url,
        )
        if settings.smtp_plaintext_auth_refused:
            audit.error(
                "email disabled: SMTP_USER is set but the connection would not be encrypted "
                "(set SMTP_STARTTLS=1 or SMTP_SSL=1, or SMTP_ALLOW_PLAINTEXT_AUTH=1 to accept the risk)"
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
