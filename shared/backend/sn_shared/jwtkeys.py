"""Ed25519 keys for the access token (`sn_token`): only `center` holds the private key, every app just verifies.

Configuration (all from the environment):

- signer (center only):  `JWT_PRIVATE_KEY` (PEM; literal `\\n` is accepted) or `JWT_PRIVATE_KEY_FILE`,
                         `JWT_KEY_ID` (default: thumbprint of the public key).
- verifiers (every app): `JWT_PUBLIC_KEYS` (one or more PEM public keys) or `JWT_PUBLIC_KEYS_FILE`.
  A key is looked up by the token's `kid` header, which is the thumbprint of the key unless a line
  `kid: <name>` precedes its PEM block (needed when center sets a custom `JWT_KEY_ID`).
- A process holding `JWT_PRIVATE_KEY` also trusts its own public key.
- Development only (`APP_ENV` is not `production`): a signer without any private key generates an ephemeral
  keypair (a warning is logged; tokens die with the process). Production: a missing key is an error.
"""

import base64
import hashlib
import logging
import os
import re
import threading
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

log = logging.getLogger("sn.jwtkeys")

ACCESS_ALGORITHM = "EdDSA"
KID_LENGTH = 16
KID_PATTERN = r"[A-Za-z0-9._-]{1,64}"
PUBLIC_BLOCK = re.compile(
    rf"(?:^[ \t]*kid[ \t]*[:=][ \t]*(?P<kid>{KID_PATTERN})[ \t]*\n)?"
    r"(?P<pem>-----BEGIN PUBLIC KEY-----.+?-----END PUBLIC KEY-----)",
    re.DOTALL | re.MULTILINE,
)
key_lock = threading.RLock()
_cache: dict[str, tuple[str, object]] = {}
_file_cache: dict[str, tuple[tuple[int, int, int], str]] = {}
_ephemeral: "Signer | None" = None


@dataclass(frozen=True)
class Signer:
    kid: str
    private_key: Ed25519PrivateKey

    @property
    def public_key(self) -> Ed25519PublicKey:
        return self.private_key.public_key()


def is_production() -> bool:
    return os.environ.get("APP_ENV", "development").strip().lower() == "production"


def thumbprint(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")[:KID_LENGTH]


def raw_jwtkeys(public_key: Ed25519PublicKey) -> bytes:
    return public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def read_jwtkeys(name: str) -> str:
    """The value of NAME, or the contents of the file named by NAME_FILE ('' when neither is set)."""
    path = os.environ.get(f"{name}_FILE", "").strip()
    if path:
        try:
            info = os.stat(path)  # re-read only when the file changes (this runs on every request)
            stamp = (info.st_mtime_ns, info.st_size, info.st_ino)  # a same-mtime atomic replace changes size/inode
            cached = _file_cache.get(path)
            if cached is not None and cached[0] == stamp:
                return cached[1]
            with open(path, encoding="utf-8") as handle:
                text = handle.read().strip()
            _file_cache[path] = (stamp, text)
            return text
        except OSError as exc:
            raise RuntimeError(f"{name}_FILE {path!r} cannot be read: {exc.strerror}") from None
    return os.environ.get(name, "").replace("\\n", "\n").strip()


def private_pem(key: Ed25519PrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


def public_pem(key: Ed25519PublicKey) -> str:
    return key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def generate_keypair() -> tuple[str, str, str]:
    """(private PEM, public PEM, kid)."""
    key = Ed25519PrivateKey.generate()
    return private_pem(key), public_pem(key.public_key()), thumbprint(key.public_key())


def load_private(pem: str) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(pem.encode(), password=None)
    except Exception as exc:  # noqa: BLE001 - any parse failure is a configuration error
        raise RuntimeError(f"JWT_PRIVATE_KEY is not a valid unencrypted PEM private key ({type(exc).__name__})") from None
    if not isinstance(key, Ed25519PrivateKey):
        raise RuntimeError("JWT_PRIVATE_KEY must be an Ed25519 key")
    return key


def memo(kind: str, source: str, build):
    with key_lock:
        hit = _cache.get(kind)
        if hit is not None and hit[0] == source:
            return hit[1]
        value = build()
        _cache[kind] = (source, value)
        return value


def get_signer() -> Signer:
    """The signing key; RuntimeError when none is configured (and an ephemeral one is not allowed)."""
    global _ephemeral
    pem = read_jwtkeys("JWT_PRIVATE_KEY")
    if pem:
        kid_override = os.environ.get("JWT_KEY_ID", "").strip()
        if kid_override and not re.fullmatch(KID_PATTERN, kid_override):
            raise RuntimeError("JWT_KEY_ID must be 1-64 characters of A-Z a-z 0-9 . _ -")

        def build() -> Signer:
            key = load_private(pem)
            return Signer(kid_override or thumbprint(key.public_key()), key)

        return memo("signer", pem + "\0" + kid_override, build)
    if is_production():
        raise RuntimeError("JWT_PRIVATE_KEY (or JWT_PRIVATE_KEY_FILE) is required in production")
    with key_lock:
        if _ephemeral is None:
            key = Ed25519PrivateKey.generate()
            _ephemeral = Signer(thumbprint(key.public_key()), key)
            log.warning(
                "no JWT_PRIVATE_KEY: using an EPHEMERAL signing key (development only; every token dies on restart)"
            )
        return _ephemeral


def parse_public_keys(text: str) -> dict[str, Ed25519PublicKey]:
    keys: dict[str, Ed25519PublicKey] = {}
    for match in PUBLIC_BLOCK.finditer(text):
        try:
            key = serialization.load_pem_public_key(match.group("pem").encode())
        except Exception:  # noqa: BLE001
            raise RuntimeError("JWT_PUBLIC_KEYS contains an unreadable PEM public key") from None
        if not isinstance(key, Ed25519PublicKey):
            raise RuntimeError("JWT_PUBLIC_KEYS must contain Ed25519 public keys only")
        kid = match.group("kid") or thumbprint(key)
        if kid in keys and raw_jwtkeys(keys[kid]) != raw_jwtkeys(key):
            raise RuntimeError(f"JWT_PUBLIC_KEYS lists the key id {kid!r} more than once")
        keys[kid] = key
    return keys


def get_verification_keys() -> dict[str, Ed25519PublicKey]:
    """kid -> public key accepted for access tokens (empty when nothing is configured)."""
    text = read_jwtkeys("JWT_PUBLIC_KEYS")
    keys: dict[str, Ed25519PublicKey] = {}
    if text:
        keys = dict(memo("public", text, lambda: parse_public_keys(text)))
        if not keys:
            raise RuntimeError("JWT_PUBLIC_KEYS holds no PEM public key")
    if read_jwtkeys("JWT_PRIVATE_KEY") or _ephemeral is not None:
        signer = get_signer()
        if signer.kid in keys and raw_jwtkeys(keys[signer.kid]) != raw_jwtkeys(signer.public_key):
            raise RuntimeError(f"JWT_KEY_ID {signer.kid!r} collides with a key id listed in JWT_PUBLIC_KEYS")
        keys[signer.kid] = signer.public_key
    return keys


def require_verification_keys() -> None:
    """Startup check for an app: production without JWT_PUBLIC_KEYS is an error, development only warns."""
    if get_verification_keys():
        return
    if is_production():
        raise RuntimeError("JWT_PUBLIC_KEYS (or JWT_PUBLIC_KEYS_FILE) is required in production")
    log.warning("no JWT_PUBLIC_KEYS: every access token will be refused (development)")


def reset() -> None:
    """Forget cached keys and the ephemeral signer (tests)."""
    global _ephemeral
    with key_lock:
        _cache.clear()
        _file_cache.clear()
        _ephemeral = None
