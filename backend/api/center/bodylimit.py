"""Streaming request-body cap (ASGI): also stops chunked bodies that have no Content-Length."""

from typing import Callable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import logging
logger = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 64 * 1024
BIOMETRIC_MAX_BYTES = 16 * 1024 * 1024
BIOMETRIC_PATHS = (
    "/auth/login/voice",
    "/auth/login/webcam",
    "/auth/login/biometric",
    "/auth/register/voice",
    "/auth/register/webcam",
    "/auth/register/combined",
    "/auth/me/voice",
    "/auth/me/webcam",
)


class BodyTooLarge(Exception):
    """The body went over the limit while being received."""


def limit_for(path: str, biometrics_enabled: bool) -> int:
    try:
        if biometrics_enabled and path in BIOMETRIC_PATHS:
            return BIOMETRIC_MAX_BYTES
        return DEFAULT_MAX_BYTES
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("limit_for failed")
        raise


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, limit: Callable[[str], int] = lambda path: DEFAULT_MAX_BYTES) -> None:
        try:
            self.app = app
            self.limit = limit
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        max_bytes = self.limit(scope.get("path", ""))
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > max_bytes:
            await self.reject(scope, receive, send)
            return
        received = 0
        exceeded = False
        started = False

        async def counting_receive() -> Message:
            try:
                nonlocal received, exceeded
                message = await receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > max_bytes:
                        exceeded = True
                        raise BodyTooLarge
                return message
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("counting_receive failed")
                raise

        async def tracking_send(message: Message) -> None:
            try:
                nonlocal started
                if exceeded:
                    return  # the app turned the error into 400/500; a 413 replaces it below
                started = started or message["type"] == "http.response.start"
                await send(message)
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("tracking_send failed")
                raise

        try:
            await self.app(scope, counting_receive, tracking_send)
        except BodyTooLarge:
            pass
        if exceeded and not started:
            await self.reject(scope, receive, send)

    async def reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await JSONResponse({"detail": "Request too large"}, status_code=413)(scope, receive, send)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("reject failed")
            raise
