from sn_shared.deps import access_dependencies
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from api.job import applicants, job_descriptions, questions
from api.job.db import Base, make_engine
from sn_shared import comments, directory, skills, tags
from sn_shared.db import ensure_columns, ensure_foreign_key, rename_table
from api.job import admin as admin_routes
from sn_shared.consumer import start_consumer, stop_consumer
from sn_shared.jwtkeys import require_verification_keys

import logging
logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL = "sqlite:///./jobs.db"

# Added to `job_descriptions` after the first release: SQL definitions, so an existing table gets them with no data lost.
JOB_DESCRIPTION_COLUMNS = {
    "company_about": "TEXT NOT NULL DEFAULT ''",
    "domain": "VARCHAR(120) NOT NULL DEFAULT ''",
    "work_mode": "VARCHAR(8) NULL",
    "timezone": "VARCHAR(60) NOT NULL DEFAULT ''",
    "working_hours": "VARCHAR(200) NOT NULL DEFAULT ''",
    "contract_until": "DATE NULL",
    "people_managed": "INTEGER NOT NULL DEFAULT 0",
    "nationality_required": "VARCHAR(60) NOT NULL DEFAULT ''",
    "requirements": "TEXT NOT NULL DEFAULT ''",
    "tags": "JSON NULL",
    "skill_keys": "JSON NULL",
    "nice_to_have": "TEXT NOT NULL DEFAULT ''",
    "hiring_process": "TEXT NOT NULL DEFAULT ''",
    "application_requirements": "TEXT NOT NULL DEFAULT ''",
}


stop_account_consumer = stop_consumer


def create_app(database_url: str | None = None) -> FastAPI:
    try:
        require_verification_keys()  # production without JWT_PUBLIC_KEYS fails at startup
        engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
        rename_table(engine, "job_applicants", "job_applications")  # the name of the table before
        Base.metadata.create_all(engine)
        ensure_foreign_key(engine, "job_applications", "job_description_id", "job_descriptions")
        ensure_columns(engine, "job_descriptions", JOB_DESCRIPTION_COLUMNS)  # postings made before these columns existed
        comments.ensure_table(engine)  # so is what people say about a thing (`sn_shared.comments`)
        skills.ensure_tables(engine)  # and the skills (`sn_shared.skills`)
        directory.ensure_table_for_sqlite(engine)  # the skills of a person are read from `users` of center (SQLite has none: an empty one)

        @asynccontextmanager
        async def lifespan(application: FastAPI) -> AsyncIterator[None]:
            handle = start_consumer("job", application.state.session_factory)
            try:
                yield
            finally:
                if handle is not None:
                    await stop_account_consumer(handle)

        app = FastAPI(title="socialnetwork jobs", lifespan=lifespan)
        app.state.session_factory = sessionmaker(engine, expire_on_commit=False)

        @app.get("/health", dependencies=access_dependencies(public=True))
        def health() -> dict[str, str]:
            try:
                return {"status": "ok"}
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("health failed")
                raise

        app.include_router(job_descriptions.router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
        app.include_router(applicants.router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
        app.include_router(questions.router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
        app.include_router(skills.skills_router(), dependencies=access_dependencies(admin=True, moderator=True, user=True))
        admin_routes.mount(app)
        return app
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("create_app failed")
        raise

