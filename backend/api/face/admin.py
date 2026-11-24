"""Admin CRUD (`/admin`) and the person's own twin (`/data`) for the measurements table (nothing depends on a row, so
the generic routes are enough)."""

from fastapi import FastAPI

from api.face.models import Measurement
from sn_shared.admincrud import TableSpec, mount_crud

SPECS = [TableSpec(Measurement, owner="user_id")]


def mount(app: FastAPI) -> None:
    mount_crud(app, SPECS, database="face")
