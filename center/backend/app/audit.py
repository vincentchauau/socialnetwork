"""Audit trail. Never pass passwords, tokens, Google ID tokens or embeddings to it."""

import logging

audit = logging.getLogger("auth.audit")
