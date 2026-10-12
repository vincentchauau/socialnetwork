import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import sessionmaker

from app.db import Base, make_engine
from app.routes_me import router as me_router
from app.routes_videos import router as videos_router
from sn_shared.security import get_jwt_secret

DEFAULT_DATABASE_URL = "sqlite:///./watch.db"
DEFAULT_UPLOAD_DIR = "./uploads"
DEFAULT_MAX_VIDEO_MB = "100"
BYTES_PER_MB = 1024 * 1024
# Multipart framing and the other form fields on top of the file itself.
MULTIPART_OVERHEAD_BYTES = BYTES_PER_MB


def create_app(database_url: str | None = None) -> FastAPI:
    get_jwt_secret()  # fail at startup, not on the first request
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)

    app = FastAPI(title="socialnetwork watch")
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.upload_dir = Path(os.environ.get("UPLOAD_DIR", DEFAULT_UPLOAD_DIR))
    app.state.max_video_bytes = int(
        float(os.environ.get("MAX_VIDEO_MB", DEFAULT_MAX_VIDEO_MB)) * BYTES_PER_MB
    )

    @app.middleware("http")
    async def reject_oversized_upload(request: Request, call_next) -> Response:
        # Refuse a declared-oversize body before it is read or spooled to disk.
        declared = request.headers.get("content-length", "")
        limit = request.app.state.max_video_bytes + MULTIPART_OVERHEAD_BYTES
        if request.method == "POST" and declared.isdigit() and int(declared) > limit:
            return JSONResponse({"detail": "Video is too large"}, status_code=413)
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(videos_router)
    app.include_router(me_router)
    return app


app = create_app()
