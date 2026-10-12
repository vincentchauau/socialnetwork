import os

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app import applications, personal, postings
from app.db import Base, make_engine
from sn_shared.security import get_jwt_secret

DEFAULT_DATABASE_URL = "sqlite:///./jobs.db"


def create_app(database_url: str | None = None) -> FastAPI:
    get_jwt_secret()  # fail at startup, not on the first request
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)

    app = FastAPI(title="socialnetwork jobs")
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(postings.router)
    app.include_router(applications.router)
    app.include_router(personal.router)
    return app


app = create_app()
