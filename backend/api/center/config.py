"""Settings read from the environment; unsafe production configuration refuses to start."""

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from api.center.audit import audit
from sn_shared import jwtkeys
from sn_shared.security import MIN_SECRET_LENGTH

DEFAULT_ORIGINS = ("http://localhost:8080",)
LOCAL_SMTP_HOSTS = ("localhost", "127.0.0.1", "::1", "mailpit")  # dev hosts where plaintext auth stays on the machine
SMTP_SSL_PORT = 465
REDIS_SCHEMES = ("redis", "rediss", "unix")


class ConfigError(RuntimeError):
    """A required setting is missing or unsafe."""


def flag(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in ("1", "true", "yes")


def positive_int(name: str, default: int) -> int:
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


def flag_default_on(name: str) -> bool:
    return os.environ.get(name, "1").strip().lower() in ("1", "true", "yes")


def float_config(name: str, default: float) -> float:
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
    liveness_required: bool = False  # LIVENESS_REQUIRED=1: every webcam sign-in/enrolment needs a liveness token
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
    redis_url: str = ""  # empty = per-process throttles/challenges; set = shared between replicas
    sms_provider: str = ""  # '' (phone features off) | 'mailbox' (DEV only) | 'twilio'
    sms_daily_cap: int = 500  # real SMS sends per 24 h, whole deployment
    sms_allowed_prefixes: tuple[str, ...] = ()  # e.g. ("+84", "+1"); empty = any E.164 number
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""

    @property
    def phone_enabled(self) -> bool:
        return bool(self.sms_provider)

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
        redis_url = os.environ.get("REDIS_URL", "").strip()
        if redis_url and urlparse(redis_url).scheme not in REDIS_SCHEMES:
            raise ConfigError("REDIS_URL must start with redis://, rediss:// or unix://")
        smtp_ssl = flag("SMTP_SSL")
        settings = Settings(
            jwt_secret=secret,
            env=env,
            cookie_secure=os.environ.get("COOKIE_SECURE") == "1",
            access_minutes=positive_int("ACCESS_TOKEN_MINUTES", 60),
            refresh_days=positive_int("REFRESH_DAYS", 14),
            allowed_origins=origins or DEFAULT_ORIGINS,
            google_client_id=os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
            biometrics_enabled=flag("BIOMETRICS_ENABLED"),
            liveness_required=flag("LIVENESS_REQUIRED"),
            data_key=os.environ.get("DATA_KEY", "").strip(),
            audio_threshold=float_config("AUDIO_THRESHOLD", 0.8),
            face_threshold=float_config("FACE_THRESHOLD", 0.6),
            audio_threshold_alone=float_config("AUDIO_THRESHOLD_ALONE", 0.88),
            face_threshold_alone=float_config("FACE_THRESHOLD_ALONE", 0.45),
            face_identify_margin=float_config("FACE_IDENTIFY_MARGIN", 0.08),
            voice_identify_margin=float_config("VOICE_IDENTIFY_MARGIN", 0.05),
            webauthn_rp_id=rp_id,
            webauthn_rp_name=os.environ.get("WEBAUTHN_RP_NAME", "").strip() or "Mạng xã hội",
            smtp_host=os.environ.get("SMTP_HOST", "").strip(),
            smtp_port=positive_int("SMTP_PORT", SMTP_SSL_PORT if smtp_ssl else 587),
            smtp_user=os.environ.get("SMTP_USER", "").strip(),
            smtp_password=os.environ.get("SMTP_PASSWORD", ""),
            smtp_from=os.environ.get("SMTP_FROM", "").strip() or "Mạng xã hội <no-reply@localhost>",
            smtp_starttls=flag_default_on("SMTP_STARTTLS"),
            smtp_ssl=smtp_ssl,
            smtp_allow_plaintext_auth=flag("SMTP_ALLOW_PLAINTEXT_AUTH"),
            public_url=public_url,
            redis_url=redis_url,
            sms_provider=os.environ.get("SMS_PROVIDER", "").strip().lower(),
            sms_daily_cap=positive_int("SMS_DAILY_CAP", 500),
            sms_allowed_prefixes=tuple(p.strip() for p in os.environ.get("SMS_ALLOWED_PREFIXES", "").split(",") if p.strip()),
            twilio_account_sid=os.environ.get("TWILIO_ACCOUNT_SID", "").strip(),
            twilio_auth_token=os.environ.get("TWILIO_AUTH_TOKEN", "").strip(),
            twilio_from=os.environ.get("TWILIO_FROM", "").strip(),
        )
        if settings.smtp_plaintext_auth_refused:
            audit.error(
                "email disabled: SMTP_USER is set but the connection would not be encrypted "
                "(set SMTP_STARTTLS=1 or SMTP_SSL=1, or SMTP_ALLOW_PLAINTEXT_AUTH=1 to accept the risk)"
            )
        settings.validate()
        if redis_url and not os.environ.get("APP_ENV", "").strip() and not (
            os.environ.get("JWT_PRIVATE_KEY", "").strip() or os.environ.get("JWT_PRIVATE_KEY_FILE", "").strip()
        ):  # a shared deployment that forgot APP_ENV must not quietly fall back to the ephemeral dev key
            raise ConfigError("REDIS_URL is set but APP_ENV is not: set APP_ENV explicitly (and a JWT_PRIVATE_KEY)")
        try:  # the access-token signing key (ephemeral in development) and any extra verification keys
            jwtkeys.get_signer()
            jwtkeys.get_verification_keys()
        except RuntimeError as exc:
            raise ConfigError(str(exc)) from None
        return settings

    def validate(self) -> None:
        if self.sms_provider not in ("", "mailbox", "twilio"):
            raise ConfigError("SMS_PROVIDER must be empty, 'mailbox' or 'twilio'")
        if self.sms_provider == "mailbox" and self.production:
            raise ConfigError("SMS_PROVIDER=mailbox is for development only and is refused in production")
        if self.sms_provider == "twilio" and self.production and not self.sms_allowed_prefixes:
            raise ConfigError("SMS_PROVIDER=twilio in production requires SMS_ALLOWED_PREFIXES (the countries you serve)")
        if self.sms_provider == "twilio" and not (self.twilio_account_sid and self.twilio_auth_token and self.twilio_from):
            raise ConfigError("SMS_PROVIDER=twilio requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM")
        if self.production and not self.cookie_secure:
            raise ConfigError("Production requires COOKIE_SECURE=1")
        if self.production and not self.webauthn_rp_id:
            raise ConfigError("Production requires WEBAUTHN_RP_ID (the domain passkeys are bound to)")
        if self.biometrics_enabled and not self.data_key:
            raise ConfigError("BIOMETRICS_ENABLED=1 requires DATA_KEY (a Fernet key)")
