"""Password hashing and JWT helpers shared by every backend.

Only `center` issues access tokens (Ed25519 / JWT alg EdDSA, see `sn_shared.jwtkeys`); every other service just
verifies them with public keys. `JWT_SECRET` (HS256) is center-private: it signs center-internal tokens
(refresh, mfa, fresh, challenges) and is never given to an app.
"""

import os
import time
from dataclasses import dataclass
from typing import Mapping

import bcrypt
import jwt

from sn_shared import jwtkeys, revocation

import logging
logger = logging.getLogger(__name__)

COOKIE_NAME = "sn_token"
ACCESS_ALGORITHM = jwtkeys.ACCESS_ALGORITHM  # EdDSA: the only algorithm accepted for the access cookie
INTERNAL_ALGORITHM = "HS256"  # center-internal tokens, signed with JWT_SECRET
ISSUER = "sn-center"
DEFAULT_TTL_SECONDS = 24 * 60 * 60
MIN_SECRET_LENGTH = 32
NON_ACCESS_TYPES = ("refresh", "mfa", "fresh")  # center-only token kinds, never valid as a session


class AuthError(Exception):
    """Raised when a token is missing, malformed, tampered with or expired."""


@dataclass(frozen=True)
class TokenPayload:
    user_id: int
    username: str
    expires_at: int
    group: str = "user"
    ver: int | None = None  # token version; center checks it in the database, other apps via the revocation store
    sid: str | None = None  # session id (device); absent on tokens issued before sessions existed


def get_jwt_secret() -> str:
    try:
        secret = os.environ.get("JWT_SECRET", "")
        if len(secret) < MIN_SECRET_LENGTH:
            raise RuntimeError(
                f"JWT_SECRET must be set and at least {MIN_SECRET_LENGTH} characters long"
            )
        return secret
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("get_jwt_secret failed")
        raise


def hash_password(password: str) -> str:
    try:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("hash_password failed")
        raise


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(
    user_id: int,
    username: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    group: str = "user",
    ver: int | None = None,
    sid: str | None = None,
) -> str:
    try:
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "sub": str(user_id),
            "username": username,
            "iat": now,
            "exp": now + ttl_seconds,
            "group": group,
        }
        if ver is not None:
            claims["ver"] = ver
        if sid is not None:
            claims["sid"] = sid
        signer = jwtkeys.get_signer()
        return jwt.encode(claims, signer.private_key, algorithm=ACCESS_ALGORITHM, headers={"kid": signer.kid})
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("create_token failed")
        raise


def verification_key(token: str):
    """The public key named by the token's `kid`; only alg EdDSA is ever accepted (no HS256/none confusion)."""
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != ACCESS_ALGORITHM:
            raise jwt.InvalidAlgorithmError("unexpected algorithm")
        kid = header.get("kid")
        key = jwtkeys.get_verification_keys().get(kid) if isinstance(kid, str) else None
        if key is None:
            raise jwt.InvalidKeyError("unknown key id")
        return key
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("verification_key failed")
        raise


def decode_token(token: str) -> TokenPayload:
    try:
        claims = jwt.decode(
            token,
            verification_key(token),
            algorithms=[ACCESS_ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "iss", "sub"]},
        )
        if claims.get("typ") in NON_ACCESS_TYPES:
            raise ValueError("not an access token")
        raw_ver = claims.get("ver")
        raw_sid = claims.get("sid")
        if raw_sid is not None and not isinstance(raw_sid, str):
            raise ValueError("bad sid")
        return TokenPayload(
            user_id=int(claims["sub"]),
            username=str(claims["username"]),
            expires_at=int(claims["exp"]),
            group=str(claims.get("group", "user")),
            ver=int(raw_ver) if raw_ver is not None else None,
            sid=raw_sid,
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise AuthError("Invalid or expired token") from exc


def payload_from_cookies(cookies: Mapping[str, str]) -> TokenPayload:
    try:
        token = cookies.get(COOKIE_NAME)
        if not token:
            raise AuthError("Not authenticated")
        payload = decode_token(token)
        if revocation.is_revoked(payload.user_id, payload.sid, payload.ver):
            raise AuthError("Token revoked")
        return payload
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("payload_from_cookies failed")
        raise
