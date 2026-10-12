from datetime import datetime
from typing import Any

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, Field, field_validator, model_validator

from app.handles import HANDLE_RE

MAX_INPUT = 1024  # hard cap on any submitted secret; the policy limit is passwords.MAX_PASSWORD
USERNAME_HINT = "Username must be 3-32 characters: a-z, 0-9, '.', '_' or '-'"


def _normalize_username(value: str) -> str:
    return value.strip().lower()


def checked_username(value: str) -> str:
    """Normalise and validate a username (raises ValueError with the user-facing hint)."""
    value = _normalize_username(value)
    if not HANDLE_RE.match(value):
        raise ValueError(USERNAME_HINT)
    return value


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
        return checked_username(value)


class LoginBody(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=MAX_INPUT)

    @field_validator("username")
    @classmethod
    def normalize(cls, value: str) -> str:
        return _normalize_username(value)


class GoogleBody(BaseModel):
    id_token: str = Field(min_length=1, max_length=4096)


class LinkGoogleBody(GoogleBody):
    password: str | None = Field(default=None, max_length=MAX_INPUT)


class ChangePasswordBody(BaseModel):
    current_password: str | None = Field(default=None, max_length=MAX_INPUT)
    new_password: str = Field(max_length=MAX_INPUT)


class DeleteAccountBody(BaseModel):
    password: str | None = Field(default=None, max_length=MAX_INPUT)


class SessionOut(BaseModel):
    id: int
    username: str
    role: str
    csrf_token: str


class MfaRequired(BaseModel):
    mfa_required: bool = True
    mfa_token: str


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


class EmailBody(BaseModel):
    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        return normalized_email(value)


class SetEmailBody(EmailBody):
    password: str | None = Field(default=None, max_length=MAX_INPUT)


class EmailVerifyBody(BaseModel):
    token: str | None = Field(default=None, max_length=256)
    code: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def exactly_one(self) -> "EmailVerifyBody":
        if bool(self.token) == bool(self.code):
            raise ValueError("Send a token or a code")
        return self


class EmailCodeBody(EmailBody):
    code: str = Field(max_length=32)


class TokenBody(BaseModel):
    token: str = Field(max_length=256)


class ResetBody(TokenBody):
    new_password: str = Field(max_length=MAX_INPUT)


class OkOut(BaseModel):
    ok: bool = True


class EmailVerifiedOut(BaseModel):
    email: str
    email_verified: bool = True
