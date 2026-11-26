from datetime import datetime
from typing import Any

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, Field, field_validator, model_validator

from api.center.handles import ALLOWED_SPECIALS, is_valid_username

import logging
logger = logging.getLogger(__name__)

MAX_INPUT = 1024  # hard cap on any submitted secret; the policy limit is passwords.MAX_PASSWORD
USERNAME_HINT = (
    f"Username must be 3-32 characters: A-Z, a-z, 0-9 or {' '.join(ALLOWED_SPECIALS)} "
    "(at least one letter or digit; no spaces or other symbols)"
)


def normalize_username(value: str) -> str:
    try:
        return value.strip()  # capitalisation is kept; identity is key_of(name)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("normalize_username failed")
        raise


def checked_username(value: str) -> str:
    """Normalise and validate a username (raises ValueError with the user-facing hint)."""
    try:
        value = normalize_username(value)
        if not is_valid_username(value):
            raise ValueError(USERNAME_HINT)
        return value
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("checked_username failed")
        raise


MAX_EMAIL = 254
EMAIL_HINT = "Enter a valid email address"


def normalized_email(value: str) -> str:
    """Strip, lowercase and syntax-check an address (no DNS lookup). Raises ValueError with a hint."""
    value = value.strip().lower()
    if not value or len(value) > MAX_EMAIL:
        raise ValueError(EMAIL_HINT)
    try:
        return validate_email(value, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise ValueError(EMAIL_HINT) from None


class Credentials(BaseModel):
    username: str
    password: str = Field(max_length=MAX_INPUT)

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        try:
            return checked_username(value)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("valid_username failed")
            raise


class LoginBody(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=MAX_INPUT)

    @field_validator("username")
    @classmethod
    def normalize(cls, value: str) -> str:
        try:
            return normalize_username(value)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("normalize failed")
            raise


class GoogleBody(BaseModel):
    id_token: str = Field(min_length=1, max_length=4096)


class LinkGoogleBody(GoogleBody):
    password: str | None = Field(default=None, max_length=MAX_INPUT)


class ChangePasswordBody(BaseModel):
    current_password: str | None = Field(default=None, max_length=MAX_INPUT)
    new_password: str = Field(max_length=MAX_INPUT)


class DeleteAccountBody(BaseModel):
    password: str | None = Field(default=None, max_length=MAX_INPUT)


class RenameBody(Credentials):
    """New username (same policy as registration) plus the password for the step-up (not needed with a fresh proof)."""

    password: str | None = Field(default=None, max_length=MAX_INPUT)


class SessionOut(BaseModel):
    id: int
    username: str
    group: str
    csrf_token: str


class MfaRequired(BaseModel):
    """Second-factor challenge. ANY ONE of `factors` ("totp", "biometric") completes the login."""

    mfa_required: bool = True
    mfa_token: str
    factors: list[str] = ["biometric"]


class MethodsStatus(BaseModel):
    has_password: bool
    google_linked: bool
    voice_login: bool
    webcam_login: bool
    has_audio: bool
    has_face: bool
    require_biometric_2fa: bool
    passkey_count: int = 0
    email_verified: bool = False
    phone: str | None = None  # masked, e.g. +84******21
    phone_verified: bool = False
    totp_enabled: bool = False
    recovery_codes_left: int = 0


class PasskeyOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None
    backed_up: bool
    transports: list[str]


class PasskeyList(BaseModel):
    passkeys: list[PasskeyOut]


class MeOut(SessionOut, MethodsStatus):
    email: str | None
    username_changed_at: datetime | None = None
    can_rename_after: datetime | None = None  # None: the username can be changed now
    passkeys: list[PasskeyOut] = []


class PasskeyOptionsBody(BaseModel):
    password: str | None = Field(default=None, max_length=MAX_INPUT)


class PasskeySignupOptionsBody(BaseModel):
    username: str | None = Field(default=None, max_length=64)


class PasskeyOptionsOut(BaseModel):
    options: dict[str, Any]
    challenge_token: str


class PasskeyLoginBody(BaseModel):
    credential: dict[str, Any]
    challenge_token: str = Field(min_length=1, max_length=4096)


class PasskeyAddBody(PasskeyLoginBody):
    name: str | None = Field(default=None, max_length=64)


class PasskeyRenameBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class AuthConfig(BaseModel):
    google_client_id: str | None
    biometrics_enabled: bool
    email_enabled: bool = False
    liveness_enabled: bool = False
    liveness_required: bool = False
    phone_enabled: bool = False


class EmailBody(BaseModel):
    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        try:
            return normalized_email(value)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("valid_email failed")
            raise


class SetEmailBody(EmailBody):
    password: str | None = Field(default=None, max_length=MAX_INPUT)


class EmailVerifyBody(BaseModel):
    token: str | None = Field(default=None, max_length=256)
    code: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def exactly_one(self) -> "EmailVerifyBody":
        try:
            if bool(self.token) == bool(self.code):
                raise ValueError("Send a token or a code")
            return self
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("exactly_one failed")
            raise


class EmailCodeBody(EmailBody):
    code: str = Field(max_length=32)


class TokenBody(BaseModel):
    token: str = Field(max_length=256)


class ResetBody(TokenBody):
    new_password: str = Field(max_length=MAX_INPUT)


class OkOut(BaseModel):
    ok: bool = True


class ReauthCodeBody(BaseModel):
    code: str = Field(max_length=32)


class FreshOut(BaseModel):
    fresh_until: datetime


class ReauthMethodsOut(BaseModel):
    methods: list[str]


class SessionItem(BaseModel):
    id: str
    current: bool
    created_at: datetime
    last_seen_at: datetime
    ip: str
    user_agent: str
    method: str


class RevokedOut(BaseModel):
    revoked: int


class EmailVerifiedOut(BaseModel):
    email: str
    email_verified: bool = True


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class TotpCodeBody(BaseModel):
    code: str = Field(max_length=MAX_INPUT)
    password: str | None = Field(default=None, max_length=MAX_INPUT)


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]
    csrf_token: str | None = None  # set when the session was re-issued (enable)


class TotpLoginBody(BaseModel):
    mfa_token: str = Field(max_length=4096)
    code: str | None = Field(default=None, max_length=MAX_INPUT)
    recovery_code: str | None = Field(default=None, max_length=MAX_INPUT)

    @model_validator(mode="after")
    def exactly_one_schemas(self):
        try:
            if (self.code is None) == (self.recovery_code is None):
                raise ValueError("Send either code or recovery_code")
            return self
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("exactly_one_schemas failed")
            raise


class QrStartOut(BaseModel):
    request_id: str
    poll_token: str
    verify_code: str
    expires_in: int
    qr_url: str


class QrPollBody(BaseModel):
    request_id: str = Field(max_length=64)
    poll_token: str = Field(max_length=128)


class QrPollOut(BaseModel):
    status: str  # pending | denied | expired


class QrInfoOut(BaseModel):  # no verify_code: the approver reads it off the NEW device's screen
    requester_ip: str
    requester_user_agent: str
    created_at: datetime
    expires_in: int


class QrApproveBody(BaseModel):
    verify_code: str = Field(max_length=16)


class QrStatusOut(BaseModel):
    status: str  # approved | denied
