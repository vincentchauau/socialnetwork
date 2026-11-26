"""One generic admin CRUD (plus data_router, its owner-scoped twin for signed-in people) router for any SQLAlchemy declarative models (admin only).

    from sn_shared.admincrud import TableSpec, admin_router
    app.include_router(admin_router([TableSpec(Spin), TableSpec(Wallet)]), prefix="/admin")

Endpoints (relative to the mount prefix): GET /tables, GET /{table}, GET /{table}/{pk}, POST /{table},
PATCH /{table}/{pk}, DELETE /{table}/{pk}. Composite primary keys are joined by "~" in the path.
"""

import logging
import os
from types import SimpleNamespace
import string
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    JSON,
    LargeBinary,
    Numeric,
    String,
    Table,
    Text,
    delete,
    column,
    func,
    insert,
    or_,
    select,
    table,
    update,
)
from sqlalchemy.sql import ClauseElement
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from sn_shared.db import get_db
from sn_shared import recordfiles
from sn_shared.deps import GROUP_ADMIN, GROUP_MODERATOR, GROUP_USER, access_dependencies, get_current_user
from sn_shared.origin import check_origin
from sn_shared.security import TokenPayload

logger = logging.getLogger("sn_shared.admincrud")

MASK = "***"
MAX_LIMIT = 100
SUGGEST_MAX = 20
GROUPS_MAX = 50  # the most values of a column a board is made from
REF_SUGGEST_LIMIT = 10
PK_SEPARATOR = "~"
TOMBSTONE_LABEL = "Người dùng đã xóa"  # a removed account keeps id 0 or a negative id in old rows
DEFAULT_USER_REF_COLUMNS = (
    "user_id", "owner_id", "seller_id", "buyer_id", "reporter_id", "actor_id", "started_by", "src_id", "dst_id",
    "blocked_id", "virtual_id", "addressee_id", "requester_id", "handled_by", "created_by",
)


MEDIA_KEYS = {"kind", "preview", "replace", "accept"}
MEDIA_KINDS = ("image", "video", "audio", "file")


@dataclass(frozen=True)
class TableSpec:
    model: Any
    # The groups that may use the table's API (anyone outside them gets "not found"). A table with an `owner` column (or a `scope`)
    # is open to the other groups for their own rows; a table without one is for the groups that manage it.
    groups: tuple[str, ...] = (GROUP_ADMIN, GROUP_MODERATOR, GROUP_USER)
    label: str | None = None
    hidden_columns: tuple[str, ...] = ()
    readonly_columns: tuple[str, ...] = ()
    secret_columns: tuple[str, ...] = ()
    # Replaces the raw DELETE: on_delete(request, db, row, admin_user) does the whole deletion inside the open
    # transaction (the router commits) and may return a callable to run after the commit (publishing, relays).
    # Raise HTTPException to refuse. `row` is the table row as a mapping.
    on_delete: Callable[..., Callable[[], None] | None] | None = None
    # Other people (not admins) reach a table only when it has an `owner` column (their own rows) or a `scope(db, user)`
    # (the rows the scope allows). They may change the rows they own; an admin changes every row.
    owner: str | None = None
    scope: Callable[[Session, TokenPayload], ClauseElement] | None = None
    user_readonly_columns: tuple[str, ...] = ()
    user_hidden_columns: tuple[str, ...] = ()
    # column -> (referenced table, label column) or (table, label column, key column; default "id"). User-ish columns
    # (DEFAULT_USER_REF_COLUMNS) refer to ("users", "username") unless listed here.
    refs: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # column -> {"kind": image|video|audio|file (default image), "preview": url template (the file to show or link),
    # "replace": url template (a PUT multipart route), "accept": mime filter}, all but kind optional. Templates hold `{column}`
    # placeholders (the frontend fills them from the row); preview "@self" means the column's own value is the image URL.
    media: dict[str, dict] = field(default_factory=dict)
    # The API path of the app's own creation route, for tables whose rows are made by an upload (not by "Add row").
    create_via: str | None = None
    create_label: str | None = None
    # The columns of `create_via`'s form fields besides the file (shown in the Add form, sent with the upload).
    create_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not set(self.groups) <= {GROUP_ADMIN, GROUP_MODERATOR, GROUP_USER} or not self.groups:
            raise ValueError("groups must be some of admin, moderator, user")
        names = {c.name for c in self.model.__table__.columns}
        for group in (self.hidden_columns, self.readonly_columns, self.secret_columns,
                      self.user_readonly_columns, self.user_hidden_columns):
            unknown = set(group) - names
            if unknown:
                raise ValueError(f"unknown columns on {self.model.__table__.name}: {sorted(unknown)}")
        unknown = set(self.refs) - names
        if unknown:
            raise ValueError(f"unknown ref columns on {self.model.__table__.name}: {sorted(unknown)}")
        for target in self.refs.values():
            if len(target) not in (2, 3) or not all(isinstance(part, str) and part for part in target):
                raise ValueError("a ref is (table, label column) or (table, label column, key column)")
        self.check_media(names)
        if self.owner is not None and self.owner not in names:
            raise ValueError(f"unknown owner column on {self.model.__table__.name}: {self.owner}")

    def check_media(self, names: set[str]) -> None:
        where = self.model.__table__.name
        unknown = set(self.media) - names
        if unknown:
            raise ValueError(f"unknown media columns on {where}: {sorted(unknown)}")
        for column, cfg in self.media.items():
            if not isinstance(cfg, dict) or set(cfg) - MEDIA_KEYS:
                raise ValueError(f"media for {where}.{column} may only hold {sorted(MEDIA_KEYS)}")
            if cfg.get("kind", "image") not in MEDIA_KINDS:
                raise ValueError(f"media kind for {where}.{column} must be one of {MEDIA_KINDS}")
            if not all(isinstance(v, str) and v for v in cfg.values()):
                raise ValueError(f"media for {where}.{column} must hold non-empty strings")
            if cfg["preview"] == "@self" and "replace" in cfg:
                raise ValueError(f"media for {where}.{column}: '@self' has no replace")
            for key in ("preview", "replace"):
                for _, field_name, _, _ in string.Formatter().parse(cfg.get(key, "")):
                    if field_name is not None and field_name not in names:
                        raise ValueError(f"media for {where}.{column} uses unknown column {field_name!r}")
        if (self.create_label is not None or self.create_fields) and self.create_via is None:
            raise ValueError("create_label and create_fields need create_via")
        unknown = set(self.create_fields) - names
        if unknown:
            raise ValueError(f"unknown create_fields on {self.model.__table__.name}: {sorted(unknown)}")

    @property
    def table(self) -> Table:
        return self.model.__table__

    def resolved_refs(self) -> dict[str, tuple[str, str, str]]:
        found = {c.name: ("users", "username", "id") for c in self.table.columns if c.name in DEFAULT_USER_REF_COLUMNS}
        for name, target in self.refs.items():
            found[name] = (target[0], target[1], target[2] if len(target) == 3 else "id")
        return found


def kind_admincrud(column: Any) -> str:
    t = column.type
    if isinstance(t, Boolean):
        return "bool"
    if isinstance(t, Integer):
        return "int"
    if isinstance(t, (Float, Numeric)):
        return "float"
    if isinstance(t, DateTime):
        return "datetime"
    if isinstance(t, JSON):
        return "json"
    if isinstance(t, LargeBinary):
        return "bytes"
    if isinstance(t, Text):
        return "text"
    return "string"


def bad(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def coerce(name: str, kind: str, value: Any) -> Any:
    try:
        if kind == "bool":
            if isinstance(value, bool):
                return value
            if value in (0, 1) and not isinstance(value, float):
                return bool(value)
            if isinstance(value, str) and value.lower() in ("true", "false", "1", "0"):
                return value.lower() in ("true", "1")
        elif kind == "int":
            if isinstance(value, bool):
                raise ValueError
            if isinstance(value, float) and not value.is_integer():
                raise ValueError
            return int(value)
        elif kind == "float":
            if isinstance(value, bool):
                raise ValueError
            return float(value)
        elif kind == "datetime":
            if isinstance(value, str):
                return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        elif kind == "json":
            return value
        elif kind in ("string", "text"):
            if isinstance(value, str):
                return value
        raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise bad(f"Column '{name}' expects {kind}") from None


def escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class Admin:
    """Introspection and row handling for one TableSpec."""

    def __init__(self, spec: TableSpec, *, user_view: bool = False) -> None:
        self.spec = spec
        self.table = spec.table
        self.name = self.table.name
        self.user_view = user_view
        # Whether the person looking may change rows of the table: an admin any row, anyone else only the rows they own.
        self.writable = not user_view or spec.owner is not None
        hidden = set(spec.hidden_columns) | (set(spec.user_hidden_columns) if user_view else set())
        self.columns = [c for c in self.table.columns if c.name not in hidden]
        self.pk = list(self.table.primary_key.columns)
        self.by_name = {c.name: c for c in self.columns}
        self.refs = {n: r for n, r in spec.resolved_refs().items() if n in self.by_name and not self.is_secret(self.by_name[n])}

    def is_secret(self, column: Any) -> bool:
        return column.name in self.spec.secret_columns or kind_admincrud(column) == "bytes"

    def is_readonly(self, column: Any) -> bool:
        if column.name in self.spec.readonly_columns:
            return True
        return self.user_view and (column.name in self.spec.user_readonly_columns or column.name == self.spec.owner)

    def describe(self) -> dict:
        return {
            "name": self.name,
            "label": self.spec.label or self.name,
            "pk": [c.name for c in self.pk],
            "groups": list(self.spec.groups),
            "writable": self.writable,
            "columns": [
                {
                    "name": c.name,
                    "type": kind_admincrud(c),
                    "nullable": bool(c.nullable),
                    "readonly": self.is_readonly(c),
                    "secret": self.is_secret(c),
                    **({"ref": {"table": self.refs[c.name][0], "label": self.refs[c.name][1], "key": self.refs[c.name][2] if len(self.refs[c.name]) > 2 else "id"}} if c.name in self.refs else {}),
                    **({"media": self.media_for(c.name)} if c.name in self.spec.media else {}),
                }
                for c in self.columns
            ],
            **({"create_via": self.spec.create_via, "create_label": self.spec.create_label or self.spec.create_via, "create_fields": list(self.spec.create_fields)} if self.spec.create_via else {}),
        }

    def media_for(self, name: str) -> dict:
        cfg = {"kind": "image", **self.spec.media[name]}
        if self.user_view:
            cfg.pop("replace", None)
        return cfg

    def out(self, row: Any) -> dict:
        result: dict[str, Any] = {}
        for c in self.columns:
            value = row[c.name]
            if self.is_secret(c):
                result[c.name] = None if value is None else MASK
            elif isinstance(value, datetime):
                result[c.name] = value.isoformat()
            else:
                result[c.name] = value
        return result

    def labels_for(self, db: Session, rows: list[dict]) -> dict[str, dict[str, str]]:
        """{column: {str(value): label}} for the values on these (already serialised) rows; never raises on a missing table."""
        result: dict[str, dict[str, str]] = {}
        for name, (ref_table, label_col, key_col) in self.refs.items():
            values = {r[name] for r in rows if r.get(name) is not None}
            found: dict[str, str] = {}
            if ref_table == "users":
                found = {str(v): TOMBSTONE_LABEL for v in values if isinstance(v, int) and not isinstance(v, bool) and v <= 0}
                values = {v for v in values if str(v) not in found}
            if values:
                ref = table(ref_table, column(key_col), column(label_col))
                stmt = select(ref.c[key_col], ref.c[label_col]).where(ref.c[key_col].in_(sorted(values, key=str)))
                try:
                    with db.begin_nested():
                        found.update({str(k): str(v) for k, v in db.execute(stmt) if v is not None})
                except SQLAlchemyError:
                    logger.debug("admincrud labels skipped for %s.%s", ref_table, name)
            if found:
                result[name] = found
        return result

    def suggest(self, db: Session, name: str, q: str, limit: int, base: list) -> dict:
        """Values (or reference options) for a column to offer while a form field is typed in; `base` limits the rows seen."""
        col = self.by_name.get(name)
        if col is None:
            raise bad(f"Unknown column '{name}'")
        is_ref = name in self.refs
        if self.is_secret(col) or self.is_readonly(col) or (not is_ref and kind_admincrud(col) not in ("string", "text")):
            raise bad(f"Column '{name}' takes no suggestions")
        term = q.strip()
        if not term:
            return {"values": [], "options": []} if is_ref else {"values": []}
        pattern = f"%{escape_like(term)}%"
        if is_ref:
            ref_table, label_col, key_col = self.refs[name]
            ref = table(ref_table, column(key_col), column(label_col))
            stmt = (
                select(ref.c[key_col], ref.c[label_col])
                .where(ref.c[label_col].ilike(pattern, escape="\\"))
                .order_by(ref.c[label_col])
                .limit(min(limit, REF_SUGGEST_LIMIT))
            )
            try:
                with db.begin_nested():
                    found = [{"value": k, "label": str(v)} for k, v in db.execute(stmt) if v is not None]
            except SQLAlchemyError:
                logger.debug("admincrud suggest skipped for %s.%s", ref_table, name)
                found = []
            return {"values": [], "options": found}
        count = func.count().label("n")
        stmt = (
            select(col, count)
            .where(col.is_not(None), col.ilike(pattern, escape="\\"), *base)
            .group_by(col)
            .order_by(count.desc(), col)
            .limit(limit)
        )
        return {"values": [str(v) for v, _ in db.execute(stmt)]}

    def groups(self, db: Session, name: str, limit: int, base: list) -> dict:
        """The values a text column holds and how many rows hold each, the most common first: what a board is made of (a status, a kind, a category)."""
        col = self.by_name.get(name)
        if col is None:
            raise bad(f"Unknown column '{name}'")
        if self.is_secret(col) or kind_admincrud(col) not in ("string", "text"):
            raise bad(f"Column '{name}' cannot be grouped by")
        count = func.count().label("n")
        stmt = select(col, count).where(col.is_not(None), col != "", *base).group_by(col).order_by(count.desc(), col).limit(limit)
        return {"values": [{"value": str(v), "count": n} for v, n in db.execute(stmt)]}

    def pk_clause(self, raw: str) -> list:
        parts = raw.split(PK_SEPARATOR)
        if len(parts) != len(self.pk):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        clause = []
        for column, part in zip(self.pk, parts):
            kind = kind_admincrud(column)
            try:
                value = coerce(column.name, kind, int(part) if kind == "int" else part)
            except (HTTPException, ValueError):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None
            clause.append(column == value)
        return clause

    def pk_text(self, row: Any) -> str:
        return PK_SEPARATOR.join(str(row[c.name]) for c in self.pk)

    def clean_values(self, values: Any, *, creating: bool) -> dict[str, Any]:
        if not isinstance(values, dict):
            raise bad("'values' must be an object")
        cleaned: dict[str, Any] = {}
        pk_names = {c.name for c in self.pk}
        for name, raw in values.items():
            column = self.by_name.get(name)
            if column is None:
                raise bad(f"Unknown column '{name}'")
            if self.is_readonly(column) or self.is_secret(column) or (not creating and name in pk_names):
                raise bad(f"Column '{name}' is not writable")
            if raw is None:
                if not column.nullable:
                    raise bad(f"Column '{name}' must not be null")
                cleaned[name] = None
            else:
                cleaned[name] = coerce(name, kind_admincrud(column), raw)
        if creating:
            for column in self.columns:
                if column.name in cleaned or self.is_readonly(column) or self.is_secret(column):
                    continue
                has_default = column.default is not None or column.server_default is not None
                auto = self.table._autoincrement_column is column
                if not column.nullable and not has_default and not auto:
                    raise bad(f"Column '{column.name}' is required")
        return cleaned


BATCH_MAX = 200  # rows per batch request


def db_error(exc: SQLAlchemyError, db: Session) -> HTTPException:
    db.rollback()
    if isinstance(exc, IntegrityError):
        return HTTPException(status.HTTP_409_CONFLICT, "Conflicts with an existing row or a constraint")
    if isinstance(exc, DataError):
        return bad("A value is not accepted by the database")
    logger.exception("admincrud database error")
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Database error")


def unknown_table() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Unknown table")


def not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


def fetch_one(db: Session, admin: Admin, clause: list) -> Any:
    row = db.execute(select(*admin.table.columns).where(*clause)).mappings().first()
    if row is None:
        raise not_found()
    return row


FILTER_PREFIX = "filter_"


def filters_of(request: Request) -> dict[str, str]:
    """The `filter_<column>=<value>` query parameters of a list request."""
    return {k[len(FILTER_PREFIX):]: v for k, v in request.query_params.items() if k.startswith(FILTER_PREFIX)}


def filter_conditions(admin: Admin, filters: dict[str, str]) -> list:
    conditions = []
    for name, raw in filters.items():
        col = admin.by_name.get(name)
        if col is None or admin.is_secret(col) or kind_admincrud(col) in ("json", "bytes"):
            raise bad(f"Cannot filter on column '{name}'")
        conditions.append(col == coerce(name, kind_admincrud(col), raw))
    return conditions


def sort_order(admin: Admin, sort: str | None) -> list:
    if not sort:
        return [c.desc() for c in admin.pk]
    name = sort.lstrip("-") if sort.startswith("-") else sort
    col = admin.by_name.get(name)
    if col is None or admin.is_secret(col) or kind_admincrud(col) in ("json", "bytes"):
        raise bad(f"Cannot sort by column '{name}'")
    return [col.desc() if sort.startswith("-") else col.asc(), *admin.pk]


SHORT_TERM_LENGTH = 3  # a shorter term, or a number, matches whole words only ("2" finds "Bag 2", not "Bag 29")


def terms_admincrud(q: str) -> list[str]:
    """The search terms of `q`: the comma-separated parts (all must match); one part may be `column:value` for a single column."""
    return [part.strip() for part in q.split(",") if part.strip()]


def list_rows_admincrud(
    admin: Admin, db: Session, q: str, offset: int, limit: int, base: list,
    sort: str | None = None, filters: dict[str, str] | None = None,
) -> dict:
    conditions = [*base, *filter_conditions(admin, filters or {})]
    order = sort_order(admin, sort)
    text_columns = [c for c in admin.columns if kind_admincrud(c) in ("string", "text") and not admin.is_secret(c)]
    for term in terms_admincrud(q):
        name, _, value = term.partition(":")
        column = next((c for c in text_columns if c.name == name.strip()), None) if value.strip() else None
        if column is not None:
            conditions.append(column.ilike(f"%{escape_like(value.strip())}%", escape="\\"))
            continue
        if not text_columns:
            return {"total": 0, "rows": []}
        escaped = escape_like(term)
        patterns = [f"%{escaped}%"] if not term.isalnum() or (len(term) >= SHORT_TERM_LENGTH and not term.isdigit()) else [escaped, f"{escaped} %", f"% {escaped}", f"% {escaped} %"]
        conditions.append(or_(*[c.ilike(pattern, escape="\\") for c in text_columns for pattern in patterns]))
    total = db.scalar(select(func.count()).select_from(admin.table).where(*conditions)) or 0
    rows = db.execute(select(*admin.table.columns).where(*conditions).order_by(*order).offset(offset).limit(limit))
    out = [admin.out(r) for r in rows.mappings()]
    return with_labels({"total": total, "rows": out}, admin, db, out)


def with_labels(payload: dict, admin: Admin, db: Session, rows: list[dict]) -> dict:
    labels = admin.labels_for(db, rows) if admin.refs and rows else {}
    return {**payload, "labels": labels} if labels else payload


def row_payload(admin: Admin, db: Session, row: Any) -> dict:
    out = admin.out(row)
    return with_labels(out, admin, db, [out])


def insert_row(admin: Admin, db: Session, values: dict) -> Any:
    try:
        result = db.execute(insert(admin.table).values(**values))
        clause = [c == v for c, v in zip(admin.pk, result.inserted_primary_key)]
        row = fetch_one(db, admin, clause)
        db.commit()
    except SQLAlchemyError as exc:
        raise db_error(exc, db) from None
    return row


def update_row_admincrud(admin: Admin, db: Session, clause: list, values: dict) -> Any:
    try:
        if values:
            db.execute(update(admin.table).where(*clause).values(**values))
        db.commit()
        return fetch_one(db, admin, clause)
    except SQLAlchemyError as exc:
        raise db_error(exc, db) from None


def delete_row_admincrud(admin: Admin, db: Session, request: Request, user: TokenPayload, clause: list, row: Any) -> None:
    after_commit = None
    try:
        if admin.spec.on_delete is not None:
            after_commit = admin.spec.on_delete(request, db, row, user)
        else:
            db.execute(delete(admin.table).where(*clause))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        raise db_error(exc, db) from None
    if after_commit is not None:
        after_commit()


def update_row(admin: Admin, db: Session, user: TokenPayload, pk: str, body: dict, *, as_admin: bool) -> dict:
    """Changes one row for a person. The rules live here, so the API routes and any other caller get the same answer:
    an admin changes any row; anyone else changes only the rows they own, and only on a table that has an owner column."""
    if as_admin:
        clause = admin.pk_clause(pk)
    else:
        if admin.spec.owner is None:
            raise HTTPException(status.HTTP_405_METHOD_NOT_ALLOWED, "Table is not editable for people")
        clause = [*admin.pk_clause(pk), admin.table.c[admin.spec.owner] == user.user_id]
    values = admin.clean_values(body.get("values", {}), creating=False)
    fetch_one(db, admin, clause)
    row = update_row_admincrud(admin, db, clause, values)
    logger.info("%s update user_id=%s table=%s pk=%s", "admin" if as_admin else "data", user.user_id, admin.name, pk)
    return admin.out(row)


def audit(user: TokenPayload, action: str, admin: Admin, pk: str, *, as_admin: bool) -> None:
    logger.info("%s %s user_id=%s table=%s pk=%s", "admin" if as_admin else "data", action, user.user_id, admin.name, pk)


def excel_rows(data: bytes) -> list[dict]:
    try:
        return recordfiles.read_excel(data, BATCH_MAX)
    except recordfiles.FileRefused as exc:
        raise bad(str(exc)) from None


def key_of(admin: Admin, values: dict) -> Any:
    """The key of a row of the Excel file (its `id`), or None when the file names none."""
    pk_names = [c.name for c in admin.pk]
    if len(pk_names) != 1 or pk_names[0] not in values or values[pk_names[0]] in (None, ""):
        return None
    return values[pk_names[0]]


def exists_admincrud(admin: Admin, db: Session, key: Any) -> bool:
    pk_column = admin.pk[0] if len(admin.pk) == 1 else None
    return key is not None and pk_column is not None and db.execute(select(pk_column).where(pk_column == key)).first() is not None


def plan_import(admin: Admin, data: bytes, db: Session) -> dict:
    """What an import would do, row by row: whether its id is already in the table (then the person chooses to overwrite it or not)."""
    rows = excel_rows(data)
    plan = []
    for index, values in enumerate(rows):
        key = key_of(admin, values)
        plan.append({"index": index, "id": key, "exists": exists_admincrud(admin, db, key)})
    return {"rows": plan, "new": sum(1 for r in plan if not r["exists"]), "existing": sum(1 for r in plan if r["exists"]), "data": rows}


def apply_import(admin: Admin, rows: list[dict], overwrite: bool, user: TokenPayload, db: Session) -> dict:
    """Creates the rows of an import. A row whose id is in the table is overwritten only when `overwrite` is set; otherwise skipped."""
    results = []
    for index, values in enumerate(rows):
        try:
            key = key_of(admin, values)
            exists = exists_admincrud(admin, db, key)
            if exists and not overwrite:
                results.append({"index": index, "status": "skipped", "id": key})
                continue
            if exists:
                rest = {k: v for k, v in values.items() if k not in {c.name for c in admin.pk}}
                clause = admin.pk_clause(str(key))
                update_row_admincrud(admin, db, clause, admin.clean_values(rest, creating=False))
                audit(user, "update", admin, str(key), as_admin=True)
                results.append({"index": index, "status": "updated", "id": key})
            else:
                row = insert_row(admin, db, admin.clean_values(values, creating=True))
                audit(user, "create", admin, admin.pk_text(row), as_admin=True)
                results.append({"index": index, "status": "created", "id": key if key is not None else admin.pk_text(row)})
        except HTTPException as exc:
            db.rollback()
            results.append({"index": index, "status": "error", "error": str(exc.detail)})
    return {"results": results, "created": sum(1 for r in results if r["status"] == "created"), "updated": sum(1 for r in results if r["status"] == "updated"), "skipped": sum(1 for r in results if r["status"] == "skipped")}


MANAGERS = (GROUP_ADMIN, GROUP_MODERATOR)  # the groups that manage the data of a table: bulk changes, imports and files


def records_router(
    models: list[TableSpec], *, get_db_dep: Callable = get_db, get_user_dep: Callable = get_current_user, database: str = "app"
) -> APIRouter:
    """The CRUD router of the records (mount at "/records"). Each table names the groups that may use it (`groups`). An admin sees and
    changes every row; anyone else sees and changes only their own rows (a table with an owner column), or the rows a table's `scope`
    allows. `?scope=all` is the admin's view, `?scope=mine` the person's own; with no `scope` an admin gets `all` and anyone else `mine`.
    Bulk changes, Excel imports and files are for the managers (admin and moderator)."""
    full = {spec.table.name: Admin(spec) for spec in models}
    own = {spec.table.name: Admin(spec, user_view=True) for spec in models if spec.owner is not None or spec.scope is not None}
    router = APIRouter(tags=["records"], dependencies=[*access_dependencies(admin=True, moderator=True, user=True), Depends(check_origin)])

    def admin_view(user: TokenPayload, scope: str | None) -> bool:
        wanted = scope or ("all" if user.group == GROUP_ADMIN else "mine")
        if wanted not in ("all", "mine"):
            raise bad("'scope' must be 'all' or 'mine'")
        if wanted == "all" and user.group != GROUP_ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin may ask for every row")
        return wanted == "all"

    def find(name: str, user: TokenPayload, as_admin: bool) -> Admin:
        found = (full if as_admin else own).get(name)
        if found is None or user.group not in found.spec.groups:
            raise unknown_table()
        return found

    def require_write(admin: Admin, as_admin: bool) -> None:
        if not as_admin and admin.spec.owner is None:
            raise HTTPException(status.HTTP_405_METHOD_NOT_ALLOWED, "Table is not editable for people")

    def visible(admin: Admin, db: Session, user: TokenPayload, as_admin: bool) -> list:
        if as_admin:
            return []
        if admin.spec.scope is not None:
            return [admin.spec.scope(db, user)]
        return [admin.table.c[admin.spec.owner] == user.user_id]

    def require_managers(user: TokenPayload, detail: str) -> None:
        if user.group not in MANAGERS:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail)

    def excel_check(table: str, file: UploadFile) -> None:
        if not any(spec.model.__tablename__ == table for spec in models):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown table")
        if os.path.splitext(file.filename or "")[1].lower() not in recordfiles.EXCEL_EXTENSIONS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Only .xlsx files can be imported")

    def media_column(table: str, column: str) -> tuple[Any, str]:
        spec = next((spec for spec in models if spec.model.__tablename__ == table), None)
        if spec is None or column not in spec.media:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a file column")
        return spec, str(spec.media[column].get("kind", "image"))

    def fetch_row(table: str, pk: str, scope: str | None, user: TokenPayload, db: Session) -> dict:
        as_admin = admin_view(user, scope)
        admin = find(table, user, as_admin)
        return row_payload(admin, db, fetch_one(db, admin, [*admin.pk_clause(pk), *visible(admin, db, user, as_admin)]))

    c = SimpleNamespace(full=full, own=own, models=models, database=database, admin_view=admin_view, find=find, require_write=require_write, visible=visible, require_managers=require_managers, excel_check=excel_check, media_column=media_column, fetch_row=fetch_row, get_user_dep=get_user_dep, get_db_dep=get_db_dep)
    read_routes(router, c)
    write_routes(router, c)
    import_routes(router, c)
    file_routes(router, c)
    return router


def read_routes(router: APIRouter, c: SimpleNamespace) -> None:
    """The read endpoints: the tables, their rows, suggestions and groups, and one row."""
    full, own, admin_view, find, visible, fetch_row, get_user_dep, get_db_dep = c.full, c.own, c.admin_view, c.find, c.visible, c.fetch_row, c.get_user_dep, c.get_db_dep
    @router.get("/tables")
    def list_tables(scope: str | None = None, user: TokenPayload = Depends(get_user_dep)) -> list[dict]:
        tables = full if admin_view(user, scope) else own
        return [admin.describe() for admin in tables.values() if user.group in admin.spec.groups]

    @router.get("/{table}")
    def list_rows(
        request: Request,
        table: str,
        q: str = "",
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=MAX_LIMIT),
        sort: str | None = None,
        scope: str | None = None,
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        as_admin = admin_view(user, scope)
        admin = find(table, user, as_admin)
        return list_rows_admincrud(admin, db, q, offset, limit, visible(admin, db, user, as_admin), sort, filters_of(request))

    @router.get("/{table}/suggest")
    def suggest(
        table: str,
        column: str,
        q: str = "",
        limit: int = Query(10, ge=1, le=SUGGEST_MAX),
        scope: str | None = None,
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        as_admin = admin_view(user, scope)
        admin = find(table, user, as_admin)
        return admin.suggest(db, column, q, limit, visible(admin, db, user, as_admin))

    @router.get("/{table}/groups")
    def groups(
        table: str,
        column: str,
        limit: int = Query(GROUPS_MAX, ge=1, le=GROUPS_MAX),
        scope: str | None = None,
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        as_admin = admin_view(user, scope)
        admin = find(table, user, as_admin)
        return admin.groups(db, column, limit, visible(admin, db, user, as_admin))

    @router.get("/{table}/{pk}")
    def get_row(table: str, pk: str, scope: str | None = None, user: TokenPayload = Depends(get_user_dep), db: Session = Depends(get_db_dep)) -> dict:
        return fetch_row(table, pk, scope, user, db)


def write_routes(router: APIRouter, c: SimpleNamespace) -> None:
    """The write endpoints: create, the Excel import, batch and single changes, delete."""
    own, admin_view, find, require_write, require_managers, excel_check, get_user_dep, get_db_dep = c.own, c.admin_view, c.find, c.require_write, c.require_managers, c.excel_check, c.get_user_dep, c.get_db_dep
    @router.post("/{table}", status_code=status.HTTP_201_CREATED)
    def create_row(
        table: str,
        body: dict = Body(...),
        scope: str | None = None,
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        as_admin = admin_view(user, scope)
        admin = find(table, user, as_admin)
        require_write(admin, as_admin)
        raw = body.get("values", {})
        if not isinstance(raw, dict):
            raise bad("'values' must be an object")
        if as_admin:
            row = insert_row(admin, db, admin.clean_values(raw, creating=True))
        else:
            owner = admin.spec.owner
            if owner in raw and raw[owner] is not None and str(raw[owner]) != str(user.user_id):
                raise bad(f"Column '{owner}' is not writable")
            values = admin.clean_values({k: v for k, v in raw.items() if k != owner}, creating=True)
            row = insert_row(admin, db, {**values, owner: user.user_id})
        audit(user, "create", admin, admin.pk_text(row), as_admin=as_admin)
        return admin.out(row)

    @router.post("/{table}/batch-update")
    def update_rows(table: str, body: dict = Body(...), user: TokenPayload = Depends(get_user_dep), db: Session = Depends(get_db_dep)) -> dict:
        """Change many rows at once (the Database tab's sheet): managers, row by row, each checked and saved on its own."""
        require_managers(user, "Only an admin or a moderator may change rows in bulk")
        admin = find(table, user, True)
        rows = body.get("rows")
        if not isinstance(rows, list) or not rows:
            raise bad("'rows' must be a non-empty list")
        if len(rows) > BATCH_MAX:
            raise bad(f"At most {BATCH_MAX} rows per request")
        results = []
        for index, item in enumerate(rows):
            try:
                pk = str(item["pk"])
                values = admin.clean_values(item.get("values", {}), creating=False)
                clause = admin.pk_clause(pk)
                fetch_one(db, admin, clause)
                update_row_admincrud(admin, db, clause, values)
                audit(user, "update", admin, pk, as_admin=True)
                results.append({"index": index, "ok": True})
            except (KeyError, TypeError) as exc:
                db.rollback()
                results.append({"index": index, "ok": False, "error": f"Each row needs a pk and values ({exc})"})
            except HTTPException as exc:
                db.rollback()
                results.append({"index": index, "ok": False, "error": str(exc.detail)})
        return {"results": results, "updated": sum(1 for r in results if r["ok"])}

    @router.patch("/{table}/{pk}")
    def patch_row(
        table: str, pk: str, body: dict = Body(...), scope: str | None = None, user: TokenPayload = Depends(get_user_dep), db: Session = Depends(get_db_dep)
    ) -> dict:
        as_admin = admin_view(user, scope)
        return update_row(find(table, user, as_admin), db, user, pk, body, as_admin=as_admin)

    @router.delete("/{table}/{pk}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_row(
        table: str,
        pk: str,
        request: Request,
        scope: str | None = None,
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> Response:
        as_admin = admin_view(user, scope)
        admin = find(table, user, as_admin)
        require_write(admin, as_admin)
        clause = admin.pk_clause(pk) if as_admin else [*admin.pk_clause(pk), admin.table.c[admin.spec.owner] == user.user_id]
        row = fetch_one(db, admin, clause)
        delete_row_admincrud(admin, db, request, user, clause, row)
        audit(user, "delete", admin, pk, as_admin=as_admin)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


def import_routes(router: APIRouter, c: SimpleNamespace) -> None:
    """The Excel import of the rows: a plan first, then the import itself (managers only)."""
    find, require_managers, excel_check, get_user_dep, get_db_dep = c.find, c.require_managers, c.excel_check, c.get_user_dep, c.get_db_dep
    @router.post("/{table}/import-plan")
    async def import_plan(table: str, file: UploadFile = File(...), user: TokenPayload = Depends(get_user_dep), db: Session = Depends(get_db_dep)) -> dict:
        """What importing this Excel file would do: how many of its rows are new and how many have an id already in the table (managers)."""
        require_managers(user, "Only an admin or a moderator may import rows")
        excel_check(table, file)
        plan = plan_import(find(table, user, True), await file.read(), db)
        return {"rows": plan["rows"], "new": plan["new"], "existing": plan["existing"]}

    @router.post("/{table}/import")
    async def import_rows(
        table: str,
        file: UploadFile = File(...),
        overwrite: bool = Form(False),
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        """Imports the rows of an Excel file (managers). A row whose id is already in the table is overwritten only when `overwrite`
        is set, else it is skipped: the rows that are not there yet are always created."""
        require_managers(user, "Only an admin or a moderator may import rows")
        excel_check(table, file)
        admin = find(table, user, True)
        plan = plan_import(admin, await file.read(), db)
        return apply_import(admin, plan["data"], overwrite, user, db)


def file_routes(router: APIRouter, c: SimpleNamespace) -> None:
    """The file cells of a row: add, list, read and delete the files."""
    database, find, require_managers, media_column, fetch_row, get_user_dep, get_db_dep = c.database, c.find, c.require_managers, c.media_column, c.fetch_row, c.get_user_dep, c.get_db_dep
    @router.post("/{table}/{pk}/files/{column}")
    async def upload_file(
        table: str,
        pk: str,
        column: str,
        file: UploadFile = File(...),
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        """Add a file to a picture, audio, video or file cell of a row (managers). All the files of a cell share one folder:
        `{database}/{table}/{column}/{row_id}/`. A file with the same name replaces the one there."""
        require_managers(user, "Only an admin or a moderator may upload files here")
        _, kind = media_column(table, column)
        # The size is checked before the file is read into memory; the bytes are checked again once read.
        try:
            recordfiles.check(kind, file.filename or "", file.size or 0)
        except recordfiles.FileRefused as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
        data = await file.read()
        try:
            name = recordfiles.check(kind, file.filename or "", len(data))
            folder = recordfiles.folder_of(database, table, column, pk)
            recordfiles.save(f"{folder}/{name}", data)
        except recordfiles.FileRefused as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
        admin = find(table, user, True)
        if row_payload(admin, db, fetch_one(db, admin, admin.pk_clause(pk))).get(column) != folder:
            update_row(admin, db, user, pk, {"values": {column: folder}}, as_admin=True)
        return row_payload(admin, db, fetch_one(db, admin, admin.pk_clause(pk)))

    @router.get("/{table}/{pk}/files/{column}")
    def list_files(
        table: str,
        pk: str,
        column: str,
        scope: str | None = None,
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        """The files of a cell, for anyone who may see the row: name, kind and the address each one is served at."""
        media_column(table, column)
        row = fetch_row(table, pk, scope, user, db)
        names = recordfiles.files_of(str(row.get(column) or ""))
        base = f"/records/{table}/{pk}/files/{column}"
        return {"files": [{"name": name.rsplit("/", 1)[-1], "kind": recordfiles.kind_of_file(name), "url": f"{base}/{name.rsplit('/', 1)[-1]}"} for name in names]}

    @router.get("/{table}/{pk}/files/{column}/{name}")
    def read_file(
        table: str,
        pk: str,
        column: str,
        name: str,
        scope: str | None = None,
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> FileResponse:
        """One file of a cell, for anyone who may see the row. Only the files the cell holds are served."""
        media_column(table, column)
        row = fetch_row(table, pk, scope, user, db)
        held = {entry.rsplit("/", 1)[-1]: entry for entry in recordfiles.files_of(str(row.get(column) or ""))}
        if name not in held:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such file here")
        target = recordfiles.location(held[name])
        if not target.is_file():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such file here")
        return FileResponse(target, media_type=recordfiles.content_type(target.name))

    @router.delete("/{table}/{pk}/files/{column}/{name}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_file(
        table: str,
        pk: str,
        column: str,
        name: str,
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> Response:
        """Remove one file of a cell (managers)."""
        require_managers(user, "Only an admin or a moderator may remove files here")
        media_column(table, column)
        admin = find(table, user, True)
        row = row_payload(admin, db, fetch_one(db, admin, admin.pk_clause(pk)))
        held = {entry.rsplit("/", 1)[-1]: entry for entry in recordfiles.files_of(str(row.get(column) or ""))}
        if name not in held:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such file here")
        recordfiles.remove(held[name])
        return Response(status_code=status.HTTP_204_NO_CONTENT)


def mount_crud(app: Any, models: list[TableSpec], *, database: str = "app") -> None:
    """Mounts a module's tables at `/records` only: admins see every row, anyone else their own (`scope` may ask for either).
    `database` names the folder of the module's files (`{database}/{table}/{column}/{row_id}/{file}`)."""
    app.include_router(records_router(models, database=database), prefix="/records")
