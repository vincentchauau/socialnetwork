from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_PASSWORD_BYTES = 72  # bcrypt ignores/rejects anything longer


class Credentials(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_]{3,32}$")
    password: str = Field(min_length=8)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()

    @field_validator("password")
    @classmethod
    def limit_password_bytes(cls, value: str) -> str:
        if len(value.encode()) > MAX_PASSWORD_BYTES:
            raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
