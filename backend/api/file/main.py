from sn_shared.deps import access_dependencies
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from api.file import files, sharing, store
from api.file.db import Base, make_engine
from api.file.paths import NotFound, PathError
from sn_shared.consumer import start_consumer, stop_consumer
from sn_shared.jwtkeys import require_verification_keys
from sn_shared.limits import UserRateLimiter

DEFAULT_DATABASE_URL = "sqlite:///./file.db"
MULTIPART_OVERHEAD_BYTES = 64 * 1024
# POST path -> largest accepted Content-Length (the real file limits are checked again while reading).
UPLOAD_LIMITS = {"/upload": files.MAX_FILE_BYTES + MULTIPART_OVERHEAD_BYTES}


def _start_account_consumer(session_factory: sessionmaker) -> Any:
    return start_consumer("file", session_factory)


_stop_account_consumer = stop_consumer


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

    app = FastAPI(title="socialnetwork file", lifespan=lifespan)
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.limiter = UserRateLimiter()  # 60 writes per minute per user

    @app.middleware("http")
    async def ensure_upload_length(request: Request, call_next) -> Response:
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

    @app.get("/health", dependencies=access_dependencies(public=True))
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(files.router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
    app.include_router(sharing.router, dependencies=access_dependencies(public=True))
    return app
