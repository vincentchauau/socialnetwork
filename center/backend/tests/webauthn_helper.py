"""A software WebAuthn authenticator for tests: real "none" attestations and real assertions.

Everything a test may want to break is a parameter: origin, rp id, challenge, counter, userHandle, flags.
"""

import base64
import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa

UP, UV, BE, BS, AT = 0x01, 0x04, 0x08, 0x10, 0x40
ES256, RS256, EDDSA = "ES256", "RS256", "EdDSA"
ORIGIN = "http://localhost:8080"
RP_ID = "localhost"
AAGUID = bytes(16)


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _int_bytes(value: int, length: int) -> bytes:
    return value.to_bytes(length, "big")


class SoftAuthenticator:
    def __init__(self, alg: str = ES256, credential_id: bytes | None = None, counter: int = 0) -> None:
        self.alg = alg
        self.credential_id = credential_id or os.urandom(32)
        self.counter = counter
        if alg == ES256:
            self.key = ec.generate_private_key(ec.SECP256R1())
        elif alg == RS256:
            self.key = rsa.generate_private_key(65537, 2048)
        else:
            self.key = ed25519.Ed25519PrivateKey.generate()

    # --- helpers ------------------------------------------------------------------------------

    def cose_key(self) -> bytes:
        public = self.key.public_key()
        if self.alg == ES256:
            numbers = public.public_numbers()
            return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: _int_bytes(numbers.x, 32), -3: _int_bytes(numbers.y, 32)})
        if self.alg == RS256:
            numbers = public.public_numbers()
            return cbor2.dumps({1: 3, 3: -257, -1: _int_bytes(numbers.n, 256), -2: _int_bytes(numbers.e, 3)})
        raw = public.public_bytes_raw()
        return cbor2.dumps({1: 1, 3: -8, -1: 6, -2: raw})

    def sign(self, data: bytes) -> bytes:
        if self.alg == ES256:
            return self.key.sign(data, ec.ECDSA(hashes.SHA256()))
        if self.alg == RS256:
            return self.key.sign(data, padding.PKCS1v15(), hashes.SHA256())
        return self.key.sign(data)

    @staticmethod
    def client_data(kind: str, challenge: bytes, origin: str) -> bytes:
        body = {"type": kind, "challenge": b64(challenge), "origin": origin, "crossOrigin": False}
        return json.dumps(body).encode()

    # --- ceremonies ---------------------------------------------------------------------------

    def create(
        self, options: dict, *, origin: str = ORIGIN, rp_id: str = RP_ID, challenge: bytes | None = None,
        flags: int = UP | UV | BE | BS, counter: int = 0, transports=("internal",), kind: str = "webauthn.create",
    ) -> dict:  # fmt: skip
        """The RegistrationResponseJSON the browser would return for `options`."""
        challenge = unb64(options["challenge"]) if challenge is None else challenge
        cose = self.cose_key()
        auth_data = (
            hashlib.sha256(rp_id.encode()).digest() + bytes([flags | AT]) + struct.pack(">I", counter)
            + AAGUID + struct.pack(">H", len(self.credential_id)) + self.credential_id + cose
        )  # fmt: skip
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        client_data = self.client_data(kind, challenge, origin)
        response = {"clientDataJSON": b64(client_data), "attestationObject": b64(attestation)}
        if transports is not None:
            response["transports"] = list(transports)
        return {
            "id": b64(self.credential_id), "rawId": b64(self.credential_id), "type": "public-key",
            "response": response, "clientExtensionResults": {}, "authenticatorAttachment": "platform",
        }  # fmt: skip

    def get(
        self, options: dict, *, user_handle: bytes | None = None, origin: str = ORIGIN, rp_id: str = RP_ID,
        challenge: bytes | None = None, flags: int = UP | UV | BE | BS, counter: int | None = None,
        kind: str = "webauthn.get", signature: bytes | None = None,
    ) -> dict:  # fmt: skip
        """The AuthenticationResponseJSON. `counter` None = increment the authenticator's own counter."""
        challenge = unb64(options["challenge"]) if challenge is None else challenge
        if counter is None:
            self.counter += 1
            counter = self.counter
        auth_data = hashlib.sha256(rp_id.encode()).digest() + bytes([flags]) + struct.pack(">I", counter)
        client_data = self.client_data(kind, challenge, origin)
        signed = auth_data + hashlib.sha256(client_data).digest()
        response = {
            "clientDataJSON": b64(client_data), "authenticatorData": b64(auth_data),
            "signature": b64(self.sign(signed) if signature is None else signature),
        }  # fmt: skip
        if user_handle is not None:
            response["userHandle"] = b64(user_handle)
        return {
            "id": b64(self.credential_id), "rawId": b64(self.credential_id), "type": "public-key",
            "response": response, "clientExtensionResults": {}, "authenticatorAttachment": "platform",
        }  # fmt: skip
