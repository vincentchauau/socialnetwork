from pydantic import BaseModel, Field, field_validator

from app.handles import HANDLE_RE

MAX_INPUT = 1024  # hard cap on any submitted secret; the policy limit is passwords.MAX_PASSWORD
USERNAME_HINT = "Username must be 3-32 characters: a-z, 0-9, '.', '_' or '-'"


def _normalize_username(value: str) -> str:
    return value.strip().lower()


class Credentials(BaseModel):
    username: str
    password: str = Field(max_length=MAX_INPUT)

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        value = _normalize_username(value)
        if not HANDLE_RE.match(value):
            raise ValueError(USERNAME_HINT)
        return value


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


class MeOut(SessionOut):
    email: str | None
    has_password: bool
    google_linked: bool
    has_audio: bool
    has_face: bool
    biometric_login: bool
    require_biometric_2fa: bool
    passwordless_ready: bool  # passwordless sign-in needs BOTH voice and face enrolled


class AuthConfig(BaseModel):
    google_client_id: str | None
    biometrics_enabled: bool


class BiometricStatus(BaseModel):
    has_audio: bool
    has_face: bool
    biometric_login: bool
    require_biometric_2fa: bool
    passwordless_ready: bool

