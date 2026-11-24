"""Hashes of the one-time tokens (email links, QR sign-in): only the hash is stored, never the token."""

import hashlib


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
