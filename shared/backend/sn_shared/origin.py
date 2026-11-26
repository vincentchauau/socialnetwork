"""Origin allow-list shared by the unsafe REST routes."""

import os

from fastapi import HTTPException, Request, status

import logging
logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_ORIGINS = "http://localhost:8080"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def allowed_origins() -> set[str]:
    try:
        raw = os.environ.get("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
        return {origin.strip() for origin in raw.split(",") if origin.strip()}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("allowed_origins failed")
        raise


def check_origin(request: Request) -> None:
    """Block cross-site writes (the auth cookie rides along): a present Origin header must be allowed.

    Same rule as center's `check_origin`; browsers always send Origin on cross-site POSTs.
    """
    try:
        if request.method not in UNSAFE_METHODS:
            return
        origin = request.headers.get("origin")
        if origin and origin not in allowed_origins():
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Origin not allowed")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("check_origin failed")
        raise
