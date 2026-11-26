"""Encrypt biometric templates at rest (Fernet = AES-128-CBC + HMAC)."""

from cryptography.fernet import Fernet, InvalidToken

from api.center.audit import audit
from api.center.config import ConfigError


class TemplateCipher:
    def __init__(self, data_key: str) -> None:
        try:
            self.fernet_snapshots = Fernet(data_key.encode())
        except (ValueError, TypeError):
            raise ConfigError("DATA_KEY is not a valid Fernet key") from None

    def encrypt(self, data: bytes) -> bytes:
        return self.fernet_snapshots.encrypt(data)

    def decrypt(self, blob: bytes) -> bytes | None:
        """None when the template is corrupt or the key changed (treated as a non-match)."""
        try:
            return self.fernet_snapshots.decrypt(blob)
        except InvalidToken:
            audit.warning("could not decrypt a stored biometric template (corrupt or DATA_KEY changed)")
            return None
