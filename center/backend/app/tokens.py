"""Center-only token kinds (refresh, mfa) and CSRF tokens bound to the access token."""

import hashlib
import hmac
import time

import jwt

from sn_shared.security import ALGORITHM, ISSUER, AuthError, get_jwt_secret


MFA_TTL_SECONDS = 5 * 60


def _make(typ: str, user_id: int, ver: int, ttl_seconds: int, **extra: str | None) -> str:
    now = int(time.time())
    claims = {"iss": ISSUER, "sub": str(user_id), "typ": typ, "ver": ver, "iat": now, "exp": now + ttl_seconds}
    claims.update({k: v for k, v in extra.items() if v is not None})
    return jwt.encode(claims, get_jwt_secret(), algorithm=ALGORITHM)


def create_refresh_token(user_id: int, ver: int, ttl_seconds: int, sid: str | None = None) -> str:
    return _make("refresh", user_id, ver, ttl_seconds, sid=sid)


def create_mfa_token(user_id: int, ver: int, ttl_seconds: int = MFA_TTL_SECONDS, method: str | None = None) -> str:
    """`method` is the primary factor already passed (it becomes the session's method after the second step)."""
    return _make("mfa", user_id, ver, ttl_seconds, mth=method)


def create_fresh_token(user_id: int, ver: int, ttl_seconds: int, sid: str | None) -> str:
    """Proof of a recent re-authentication, bound to one user and one session."""
    return _make("fresh", user_id, ver, ttl_seconds, sid=sid)


def decode_claims(token: str, typ: str) -> dict:
    """The verified claims of a token of the given kind; AuthError for anything else."""
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
        int(claims["sub"]), int(claims["ver"])
        for optional in ("sid", "mth"):
            if optional in claims and not isinstance(claims[optional], str):
                raise ValueError(f"bad {optional}")
        return claims
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        raise AuthError("Invalid or expired token") from exc


def decode_typed(token: str, typ: str) -> tuple[int, int]:
    """(user_id, ver) of a token of the given kind; AuthError for anything else."""
    claims = decode_claims(token, typ)
    return int(claims["sub"]), int(claims["ver"])


def csrf_token(session_token: str) -> str:
    """HMAC (under a sub-key, not the JWT key itself) of the access token."""
    key = hmac.new(get_jwt_secret().encode(), b"csrf-subkey", hashlib.sha256).digest()
    return hmac.new(key, session_token.encode(), hashlib.sha256).hexdigest()


def csrf_valid(presented: str | None, session_token: str) -> bool:
    return bool(presented) and hmac.compare_digest(presented or "", csrf_token(session_token))
