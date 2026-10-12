"""Password hashing and JWT helpers shared by every backend.

Only `center` issues tokens; every other service just verifies them.
"""

import os
import time
from dataclasses import dataclass
from typing import Mapping

import bcrypt
import jwt

COOKIE_NAME = "sn_token"
ALGORITHM = "HS256"
ISSUER = "sn-center"
DEFAULT_TTL_SECONDS = 24 * 60 * 60
MIN_SECRET_LENGTH = 32
NON_ACCESS_TYPES = ("refresh", "mfa")  # center-only token kinds, never valid as a session


class AuthError(Exception):
    """Raised when a token is missing, malformed, tampered with or expired."""


@dataclass(frozen=True)
class TokenPayload:
    user_id: int
    username: str
    expires_at: int
    role: str = "user"
    ver: int | None = None  # token version; only center checks it


def get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET", "")
    if len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET must be set and at least {MIN_SECRET_LENGTH} characters long"
        )
    return secret


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(
    user_id: int,
    username: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    role: str = "user",
    ver: int | None = None,
) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": str(user_id),
        "username": username,
        "iat": now,
        "exp": now + ttl_seconds,
        "role": role,
    }
    if ver is not None:
        claims["ver"] = ver
    return jwt.encode(claims, get_jwt_secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> TokenPayload:
    try:
        claims = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "iss", "sub"]},
        )
        if claims.get("typ") in NON_ACCESS_TYPES:
            raise ValueError("not an access token")
        raw_ver = claims.get("ver")
        return TokenPayload(
            user_id=int(claims["sub"]),
            username=str(claims["username"]),
            expires_at=int(claims["exp"]),
            role=str(claims.get("role", "user")),
            ver=int(raw_ver) if raw_ver is not None else None,
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise AuthError("Invalid or expired token") from exc


def payload_from_cookies(cookies: Mapping[str, str]) -> TokenPayload:
    token = cookies.get(COOKIE_NAME)
    if not token:
        raise AuthError("Not authenticated")
    return decode_token(token)
