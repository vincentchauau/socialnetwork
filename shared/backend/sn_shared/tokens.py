"""Hashes of the one-time tokens (email links, QR sign-in): only the hash is stored, never the token."""

import hashlib

import logging
logger = logging.getLogger(__name__)


def hash_token(token: str) -> str:
    try:
        return hashlib.sha256(token.encode()).hexdigest()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("hash_token failed")
        raise
