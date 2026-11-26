from sn_shared.deps import access_dependencies
"""Several services in one process: each stays the application it was, mounted under its own path, with its own database.

`host("core", {"market": create_market, ...})` makes the application of a hosting service. A module's database is the one given
(tests), else `<NAME>_DATABASE_URL`, else the module's own default. The lifespan of every module runs inside the host's, so their
account-event consumers start and stop with it; a module that cannot start stops the whole host (a half-working one hides it).
"""

import os
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from sn_shared.db import make_engine, retire_columns

import logging
logger = logging.getLogger(__name__)


def database_of(name: str, urls: dict[str, str] | None) -> str | None:
    try:
        return (urls or {}).get(name) or os.environ.get("DATABASE_URL") or None  # one database for every module
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("database_of failed")
        raise


def host(
    title: str, makers: dict[str, Callable[..., FastAPI]], database_urls: dict[str, str] | None = None,
    legacy_columns: dict[str, list[str]] | None = None,
) -> FastAPI:
    try:
        if legacy_columns:  # columns the code dropped, still in a database made before (see `retire_columns`)
            for name in makers:
                url = database_of(name, database_urls)
                if url:
                    engine = make_engine(url)
                    retire_columns(engine, legacy_columns)
                    engine.dispose()
        modules = {name: make(database_of(name, database_urls)) for name, make in makers.items()}

        @asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncIterator[None]:
            try:
                async with AsyncExitStack() as stack:
                    for module in modules.values():
                        await stack.enter_async_context(module.router.lifespan_context(module))
                    yield
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("lifespan failed")
                raise

        app = FastAPI(title=title, lifespan=lifespan, docs_url=None)
        app.state.modules = modules

        @app.get("/health", dependencies=access_dependencies(public=True))
        def health() -> dict[str, str]:
            try:
                return {"status": "ok"}
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("health failed")
                raise

        for name, module in modules.items():
            app.mount(f"/{name}", module)
        return app
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("host failed")
        raise
