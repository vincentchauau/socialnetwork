"""The backend: every module of the social network in one process.

Each module is the application it was (its routes, its limits, its account events) mounted under its own path, and keeps its own
database (`DATABASE_URL`, one for every module). The gateway sends `/api/chat/...` to `/chat/...` here.
Modules do not read each other's tables: they call each other's routes (the agent calls market and the others for the person who asked),
and the account events of the center reach each module's own handlers.
"""

import os
from collections.abc import Callable

from fastapi import FastAPI
from sn_shared.hosting import host

from api.center.main import create_app as create_center
from api.chat.main import create_app as create_chat
from api.face.main import create_app as create_face
from api.roulette.main import create_app as create_roulette
from api.market.main import create_app as create_market
from api.job.main import create_app as create_job
from api.werewolf.main import create_app as create_werewolf
from api.file.main import create_app as create_file

import logging
logger = logging.getLogger(__name__)

MODULES: dict[str, Callable[..., FastAPI]] = {
    "center": create_center,
    "chat": create_chat,
    "werewolf": create_werewolf,
    "file": create_file,
    "face": create_face,
    "roulette": create_roulette,
    "market": create_market,
    "job": create_job,
}


# Columns the modules no longer have (the names are read from `users`; the rest can be worked out): an older database still has them.
LEGACY_COLUMNS: dict[str, list[str]] = {
    "market_products": ["seller_username", "updated_at"],
    "market_orders": ["buyer_username", "updated_at", "currency"],
    "roulette_spins": ["colour"],
    "messages": ["username", "deleted_by"],
    "job_descriptions": ["owner_username"],
    "job_applications": ["username"],
    "courses": ["owner_username"],
    "comments": ["username"],
    "roulette_wallets": ["username", "updated_at"],
    "enrollments": ["username", "enrolled_at"],
    "games": ["saved_at"],
    "skills": ["uses"],
    "reports": ["handled_at", "handled_by"],
    "room_members": ["username", "status_by", "verified", "attributes"],
    "rooms": ["ref_type", "ref_id", "icon"],
    "users": ["biometric_login", "alias", "gender", "nationality", "postal_code", "website", "timezone", "preferred_language",
              "open_to_work", "desired_title", "desired_salary_min", "desired_salary_max", "salary_currency", "available_from"],
}


def create_app(database_urls: dict[str, str] | None = None) -> FastAPI:
    try:
        return host("socialnetwork", MODULES, database_urls, legacy_columns=LEGACY_COLUMNS)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("create_app failed")
        raise


app = create_app() if os.environ.get("DATABASE_URL") else None  # type: ignore[assignment]
