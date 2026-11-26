"""WebAuthn (passkey) building blocks: challenge tokens, single-use tracking, option builders, verification.

Challenges are stateless signed tokens (`typ="webauthn"`) that carry the challenge and what it was minted
for. They are also SINGLE USE: consumed `jti`s are remembered in `ChallengeStore`, a TTL marker in the Kv
(Redis-backed when REDIS_URL is set, so replicas share it; per process otherwise, or while Redis is down: a
token could then be replayed once per replica within its 5 minutes).

Security stance: user verification REQUIRED, discoverable credentials REQUIRED, attestation "none",
ES256 / RS256 / EdDSA only. Callers never report WHY a verification failed.
"""

import secrets
import time
from dataclasses import dataclass
from typing import Any

import jwt
from webauthn import generate_authentication_options, generate_registration_options
from webauthn import verify_authentication_response, verify_registration_response
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.options_to_json_dict import options_to_json_dict
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from api.center.config import Settings
from api.center.kv import Kv
from api.center.models import Passkey, User
from sn_shared.security import INTERNAL_ALGORITHM, ISSUER, get_jwt_secret

import logging
logger = logging.getLogger(__name__)

CHALLENGE_TTL_SECONDS = 5 * 60
CHALLENGE_TYP = "webauthn"
SIGNUP, LINK, LOGIN, REAUTH = "signup", "link", "login", "reauth"
PURPOSES = (SIGNUP, LINK, LOGIN, REAUTH)
USER_HANDLE_BYTES = 32
DEFAULT_PASSKEY_NAME = "Passkey"
MAX_TRANSPORTS_LENGTH = 100
CONSUMED_PREFIX = "passkey-jti:"
SUPPORTED_ALGORITHMS = [
    COSEAlgorithmIdentifier.ECDSA_SHA_256,  # ES256
    COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,  # RS256
    COSEAlgorithmIdentifier.EDDSA,
]
TRANSPORT_VALUES = {t.value for t in AuthenticatorTransport}


class PasskeyError(Exception):
    """Any problem with a challenge token or a WebAuthn response (never shown to the client in detail)."""


class ChallengeStore:
    """Consumed challenge ids, kept until their token would have expired anyway (shared when the Kv is)."""

    def __init__(self, kv: Kv, now=time.time) -> None:
        try:
            self._kv = kv
            self.now_totp = now
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    def consume(self, jti: str, expires_at: float) -> bool:
        """True the first time `jti` is seen. Fails closed (False) when the token is expired or the store is full."""
        try:
            ttl = expires_at - self.now_totp()
            return ttl > 0 and self._kv.set_if_absent(f"{CONSUMED_PREFIX}{jti}", ttl)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("consume failed")
            raise


@dataclass(frozen=True)
class Challenge:
    purpose: str
    challenge: bytes
    user_id: int | None
    user_handle: bytes | None
    username: str | None
    jti: str
    expires_at: int


def mint_challenge(
    purpose: str, challenge: bytes, *, user_id: int | None = None, user_handle: bytes | None = None,
    username: str | None = None, ttl_seconds: int = CHALLENGE_TTL_SECONDS,
) -> str:  # fmt: skip
    try:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER, "typ": CHALLENGE_TYP, "purpose": purpose, "chal": bytes_to_base64url(challenge),
            "jti": secrets.token_urlsafe(16), "iat": now, "exp": now + ttl_seconds,
        }  # fmt: skip
        # No `sub`: this token can never pass as an access token.
        if user_id is not None:
            claims["uid"] = user_id
        if user_handle is not None:
            claims["uh"] = bytes_to_base64url(user_handle)
        if username is not None:
            claims["uname"] = username
        return jwt.encode(claims, get_jwt_secret(), algorithm=INTERNAL_ALGORITHM)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("mint_challenge failed")
        raise


def read_challenge(token: str, purpose: str, store: ChallengeStore) -> Challenge:
    """Verify signature, expiry, kind and purpose, then consume it (single use). PasskeyError otherwise."""
    try:
        claims = jwt.decode(
            token, get_jwt_secret(), algorithms=[INTERNAL_ALGORITHM], issuer=ISSUER,
            options={"require": ["exp", "iss", "jti", "chal", "purpose"]},
        )  # fmt: skip
        if claims.get("typ") != CHALLENGE_TYP or claims["purpose"] != purpose:
            raise PasskeyError("wrong token")
        handle = claims.get("uh")
        found = Challenge(
            purpose=purpose,
            challenge=base64url_to_bytes(claims["chal"]),
            user_id=int(claims["uid"]) if "uid" in claims else None,
            user_handle=base64url_to_bytes(handle) if handle else None,
            username=claims.get("uname"),
            jti=str(claims["jti"]),
            expires_at=int(claims["exp"]),
        )
    except PasskeyError:
        raise
    except Exception as exc:  # malformed token / claims: all the same
        raise PasskeyError("invalid token") from exc
    if not store.consume(found.jti, found.expires_at):
        raise PasskeyError("token already used")
    return found


def new_user_handle() -> bytes:
    try:
        return secrets.token_bytes(USER_HANDLE_BYTES)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("new_user_handle failed")
        raise


def user_handle_of(user: User) -> bytes | None:
    try:
        return user.passkeys[0].user_handle if user.passkeys else None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("user_handle_of failed")
        raise


def descriptor(passkey: Passkey) -> PublicKeyCredentialDescriptor:
    try:
        return PublicKeyCredentialDescriptor(id=passkey.credential_id, transports=transports_of(passkey) or None)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("descriptor failed")
        raise


def transports_of(passkey: Passkey) -> list[AuthenticatorTransport]:
    try:
        return [AuthenticatorTransport(v) for v in (passkey.transports or "").split(",") if v in TRANSPORT_VALUES]
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("transports_of failed")
        raise


def creation_options(
    settings: Settings, *, user_name: str, display_name: str, user_handle: bytes,
    existing: list[Passkey] | None = None,
) -> tuple[dict, bytes]:  # fmt: skip
    """(PublicKeyCredentialCreationOptionsJSON, challenge)."""
    try:
        options = generate_registration_options(
            rp_id=settings.webauthn_rp_id,
            rp_name=settings.webauthn_rp_name,
            user_name=user_name,
            user_display_name=display_name,
            user_id=user_handle,
            attestation=AttestationConveyancePreference.NONE,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=[descriptor(p) for p in existing or []],
            supported_pub_key_algs=SUPPORTED_ALGORITHMS,
        )
        return options_to_json_dict(options), options.challenge
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("creation_options failed")
        raise


def request_options(settings: Settings) -> tuple[dict, bytes]:
    """(PublicKeyCredentialRequestOptionsJSON with an empty allowCredentials, challenge)."""
    try:
        options = generate_authentication_options(
            rp_id=settings.webauthn_rp_id,
            allow_credentials=[],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        return options_to_json_dict(options), options.challenge
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("request_options failed")
        raise


def sanitized_transports(credential: Any) -> str | None:
    try:
        response = credential.get("response") if isinstance(credential, dict) else None
        raw = response.get("transports") if isinstance(response, dict) else None
        if not isinstance(raw, list):
            return None
        kept = [t for t in dict.fromkeys(raw) if isinstance(t, str) and t in TRANSPORT_VALUES]
        joined = ",".join(kept)
        return joined[:MAX_TRANSPORTS_LENGTH].rstrip(",") or None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("sanitized_transports failed")
        raise


def verify_registration(settings: Settings, credential: Any, challenge: Challenge) -> dict:
    """Verify a creation response; returns the Passkey column values. PasskeyError on any problem."""
    if not isinstance(credential, dict) or challenge.user_handle is None:
        raise PasskeyError("bad registration")
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge.challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=list(settings.webauthn_origins),
            require_user_verification=True,
            supported_pub_key_algs=SUPPORTED_ALGORITHMS,
        )
    except Exception as exc:
        raise PasskeyError("registration not verified") from exc
    return {
        "credential_id": verified.credential_id,
        "public_key": verified.credential_public_key,
        "sign_count": verified.sign_count,
        "user_handle": challenge.user_handle,
        "transports": sanitized_transports(credential),
        "backed_up": bool(verified.credential_backed_up),
    }


@dataclass(frozen=True)
class Assertion:
    passkey_credential_id: bytes
    new_sign_count: int
    backed_up: bool


def credential_id_of(credential: Any) -> bytes:
    """The raw credential id the browser reports (PasskeyError when it is missing or malformed)."""
    try:
        return base64url_to_bytes(credential["rawId"])
    except Exception as exc:
        raise PasskeyError("bad credential id") from exc


def verify_assertion(settings: Settings, credential: Any, challenge: Challenge, passkey: Passkey) -> Assertion:
    """Verify a sign-in response against the stored passkey (PasskeyError on any problem).

    The sign counter is checked by the caller (it audits a cloned authenticator), so the library check is
    neutralised by passing 0 as the current count.
    """
    try:
        response = credential["response"]
        handle = response.get("userHandle")
        if handle is not None and (
            not isinstance(handle, str) or not secrets.compare_digest(base64url_to_bytes(handle), passkey.user_handle)
        ):
            raise PasskeyError("user handle mismatch")
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge.challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=list(settings.webauthn_origins),
            credential_public_key=passkey.public_key,
            credential_current_sign_count=0,
            require_user_verification=True,
        )
    except PasskeyError:
        raise
    except Exception as exc:
        raise PasskeyError("assertion not verified") from exc
    return Assertion(verified.credential_id, verified.new_sign_count, bool(verified.credential_backed_up))


def sign_count_regressed(stored: int, new: int) -> bool:
    """Many passkeys always report 0 (allowed); otherwise the counter must strictly increase."""
    try:
        return (stored > 0 or new > 0) and new <= stored
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("sign_count_regressed failed")
        raise
