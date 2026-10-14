"""Database manager routes: a private SQLite file per user (see app/sqlbox.py)."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from app import sqlbox, store
from app.deps import db_reader, writer
from app.security import check_origin
from sn_shared.security import TokenPayload

router = APIRouter(dependencies=[Depends(check_origin)])


class QueryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str = Field(min_length=1, max_length=sqlbox.MAX_SQL_CHARS)


def _run(user_id: int, function, *args):
    """Run one sandbox operation under the user's lock; DbError / Busy become HTTP errors."""
    try:
        with store.user_lock(user_id):
            return function(store.db_path(user_id), *args)
    except sqlbox.DbError as error:
        raise HTTPException(error.status, error.detail) from None
    except store.Busy:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Cơ sở dữ liệu đang bận, hãy thử lại sau") from None


@router.get("/db/tables")
def tables(user: TokenPayload = Depends(db_reader)) -> list[dict]:
    return _run(user.user_id, sqlbox.list_tables)


@router.get("/db/tables/{name}")
def table_rows(
    name: Annotated[str, Path(min_length=1, max_length=64)],
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=sqlbox.MAX_PAGE_SIZE)] = 50,
    q: Annotated[str, Query(max_length=200)] = "",
    user: TokenPayload = Depends(db_reader),
) -> dict:
    return _run(user.user_id, sqlbox.browse, name, page, page_size, q)


@router.post("/db/query")
def query(body: QueryIn, user: TokenPayload = Depends(writer)) -> dict:
    return _run(user.user_id, sqlbox.run_query, body.sql)


@router.post("/db/import", status_code=status.HTTP_201_CREATED)
def import_csv(
    file: Annotated[UploadFile, File()],
    table: Annotated[str, Form(max_length=100)],
    user: TokenPayload = Depends(writer),
) -> dict:
    data = file.file.read(sqlbox.MAX_IMPORT_BYTES + 1)
    return _run(user.user_id, sqlbox.import_csv, table, data)


@router.get("/db/export")
def export(
    table: Annotated[str, Query(min_length=1, max_length=64)],
    user: TokenPayload = Depends(db_reader),
) -> Response:
    data = _run(user.user_id, sqlbox.export_csv, table)
    filename = re.sub(r"[^A-Za-z0-9_.-]", "_", table)
    return Response(
        data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.csv"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/db", status_code=status.HTTP_204_NO_CONTENT)
def drop(user: TokenPayload = Depends(writer)) -> Response:
    _run(user.user_id, sqlbox.delete_database)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
