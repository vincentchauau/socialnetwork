"""Admin CRUD (`/admin`) and the person's own twin (`/data`) for the measurements table (nothing depends on a row, so
the generic routes are enough)."""

from fastapi import FastAPI

from api.face.models import Measurement
from sn_shared.admincrud import TableSpec, mount_crud

import logging
logger = logging.getLogger(__name__)

SPECS = [TableSpec(Measurement, owner="user_id")]


def mount(app: FastAPI) -> None:
    try:
        mount_crud(app, SPECS, database="face")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("mount failed")
        raise
