"""Center-only token kinds (refresh, mfa) and CSRF tokens bound to the access token."""

import hashlib
import hmac
import time

import jwt

from sn_shared.security import ALGORITHM, ISSUER, AuthError, get_jwt_secret


MFA_TTL_SECONDS = 5 * 60


def _make(typ: str, user_id: int, ver: int, ttl_seconds: int) -> str:
    now = int(time.time())
    claims = {"iss": ISSUER, "sub": str(user_id), "typ": typ, "ver": ver, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(claims, get_jwt_secret(), algorithm=ALGORITHM)


def create_refresh_token(user_id: int, ver: int, ttl_seconds: int) -> str:
    return _make("refresh", user_id, ver, ttl_seconds)


def create_mfa_token(user_id: int, ver: int, ttl_seconds: int = MFA_TTL_SECONDS) -> str:
    return _make("mfa", user_id, ver, ttl_seconds)


def decode_typed(token: str, typ: str) -> tuple[int, int]:
    """(user_id, ver) of a token of the given kind; AuthError for anything else."""
    try:
        claims = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "iss", "sub", "ver"]},
        )
        if claims.get("typ") != typ:
            raise ValueError("wrong token type")
        return int(claims["sub"]), int(claims["ver"])
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        raise AuthError("Invalid or expired token") from exc


def csrf_token(session_token: str) -> str:
    """HMAC (under a sub-key, not the JWT key itself) of the access token."""
    key = hmac.new(get_jwt_secret().encode(), b"csrf-subkey", hashlib.sha256).digest()
    return hmac.new(key, session_token.encode(), hashlib.sha256).hexdigest()


def csrf_valid(presented: str | None, session_token: str) -> bool:
    return bool(presented) and hmac.compare_digest(presented or "", csrf_token(session_token))
