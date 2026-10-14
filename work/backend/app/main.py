import inspect
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from app import dbroutes, files, sqlbox, store, telnyx
from app.db import Base, make_engine
from app.limits import UserRateLimiter
from app.paths import NotFound, PathError
from sn_shared.jwtkeys import require_verification_keys

DEFAULT_DATABASE_URL = "sqlite:///./work.db"
MULTIPART_OVERHEAD_BYTES = 64 * 1024
READ_LIMIT_PER_MINUTE = 240
# POST path -> largest accepted Content-Length (the real file limits are checked again while reading).
UPLOAD_LIMITS = {
    "/files/upload": files.MAX_FILE_BYTES + MULTIPART_OVERHEAD_BYTES,
    "/db/import": sqlbox.MAX_IMPORT_BYTES + MULTIPART_OVERHEAD_BYTES,
}


def _start_account_consumer(session_factory: sessionmaker) -> Any:
    """Start center's account-event consumer; None in tests, without Redis or without the library."""
    if os.environ.get("TESTING") or not os.environ.get("REDIS_URL"):
        return None
    try:
        from sn_shared.events import start_account_consumer
    except ImportError:
        return None
    return start_account_consumer("work", session_factory)


async def _stop_account_consumer(handle: Any) -> None:
    stop = getattr(handle, "stop", None) or getattr(handle, "close", None)
    if stop is None:
        return
    result = stop()
    if inspect.isawaitable(result):
        await result


def create_app(database_url: str | None = None) -> FastAPI:
    require_verification_keys()  # production without JWT_PUBLIC_KEYS fails at startup
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        handle = _start_account_consumer(application.state.session_factory)
        try:
            yield
        finally:
            if handle is not None:
                await _stop_account_consumer(handle)

    app = FastAPI(title="socialnetwork work", lifespan=lifespan)
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.limiter = UserRateLimiter()  # 60 writes per minute per user
    app.state.read_limiter = UserRateLimiter(max_events=READ_LIMIT_PER_MINUTE)
    app.state.telnyx_transport = None  # tests inject an httpx.MockTransport

    @app.middleware("http")
    async def require_upload_length(request: Request, call_next) -> Response:
        # Chunked bodies carry no Content-Length and would bypass size checks.
        limit = UPLOAD_LIMITS.get(request.url.path) if request.method == "POST" else None
        if limit is not None:
            declared = request.headers.get("content-length", "")
            if not declared.isdigit():
                return JSONResponse({"detail": "Cần có tiêu đề Content-Length"}, status_code=411)
            if int(declared) > limit:
                return JSONResponse({"detail": "Tệp quá lớn"}, status_code=413)
        return await call_next(request)

    @app.exception_handler(PathError)
    async def bad_path(_request: Request, error: PathError) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.exception_handler(NotFound)
    async def missing(_request: Request, _error: NotFound) -> JSONResponse:
        return JSONResponse({"detail": "Không tìm thấy"}, status_code=404)

    @app.exception_handler(store.Busy)
    async def busy(_request: Request, _error: store.Busy) -> JSONResponse:
        return JSONResponse({"detail": "Hệ thống đang bận, hãy thử lại sau"}, status_code=429)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(files.router)
    app.include_router(dbroutes.router)
    app.include_router(telnyx.router)
    return app


app = create_app()
