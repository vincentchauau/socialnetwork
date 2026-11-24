"""One generic admin CRUD (plus data_router, its owner-scoped twin for signed-in people) router for any SQLAlchemy declarative models (admin only).

    from sn_shared.admincrud import TableSpec, admin_router
    app.include_router(admin_router([TableSpec(Spin), TableSpec(Wallet)]), prefix="/admin")

Endpoints (relative to the mount prefix): GET /tables, GET /{table}, GET /{table}/{pk}, POST /{table},
PATCH /{table}/{pk}, DELETE /{table}/{pk}. Composite primary keys are joined by "~" in the path.
"""

import logging
import os
import string
from types import SimpleNamespace
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
from sn_shared.deps import GROUP_ADMIN, access_dependencies, get_current_user
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
MODES = ("crud", "edit-delete", "read-delete")  # edit-delete: rows are made elsewhere (a payment, a checkout), an admin may fix and remove them


MEDIA_KEYS = {"kind", "preview", "replace", "accept"}
MEDIA_KINDS = ("image", "video", "audio", "file")


@dataclass(frozen=True)
class TableSpec:
    model: Any
    mode: str = "crud"
    label: str | None = None
    hidden_columns: tuple[str, ...] = ()
    readonly_columns: tuple[str, ...] = ()
    secret_columns: tuple[str, ...] = ()
    # Replaces the raw DELETE: on_delete(request, db, row, admin_user) does the whole deletion inside the open
    # transaction (the router commits) and may return a callable to run after the commit (publishing, relays).
    # Raise HTTPException to refuse. `row` is the table row as a mapping.
    on_delete: Callable[..., Callable[[], None] | None] | None = None
    # User-facing /data twin (see data_router). `owner` is the column holding the owner's user id; `user_ops` is a
    # subset of "RCUD" an ordinary person may do; `scope(db, user)` replaces the owner filter for reads.
    owner: str | None = None
    user_ops: str = ""
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
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
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
        self._check_media(names)
        if self.owner is not None and self.owner not in names:
            raise ValueError(f"unknown owner column on {self.model.__table__.name}: {self.owner}")
        if set(self.user_ops) - set("RCUD"):
            raise ValueError("user_ops must be a subset of 'RCUD'")
        if self.user_ops and self.owner is None and self.scope is None:
            raise ValueError("user_ops needs an owner column or a scope")
        if set(self.user_ops) & set("CUD") and self.owner is None:
            raise ValueError("user_ops C/U/D needs an owner column")

    def _check_media(self, names: set[str]) -> None:
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


def _kind(column: Any) -> str:
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


def _bad(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail)


def _coerce(name: str, kind: str, value: Any) -> Any:
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
        raise _bad(f"Column '{name}' expects {kind}") from None


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class _Admin:
    """Introspection and row handling for one TableSpec."""

    def __init__(self, spec: TableSpec, *, user_view: bool = False) -> None:
        self.spec = spec
        self.table = spec.table
        self.name = self.table.name
        self.user_view = user_view
        hidden = set(spec.hidden_columns) | (set(spec.user_hidden_columns) if user_view else set())
        self.user_ops = "".join(op for op in "RCUD" if op in spec.user_ops and (spec.mode == "crud" or op in ("RD" if spec.mode == "read-delete" else "RUD")))
        self.columns = [c for c in self.table.columns if c.name not in hidden]
        self.pk = list(self.table.primary_key.columns)
        self.by_name = {c.name: c for c in self.columns}
        self.refs = {n: r for n, r in spec.resolved_refs().items() if n in self.by_name and not self.is_secret(self.by_name[n])}

    def is_secret(self, column: Any) -> bool:
        return column.name in self.spec.secret_columns or _kind(column) == "bytes"

    def is_readonly(self, column: Any) -> bool:
        if column.name in self.spec.readonly_columns:
            return True
        return self.user_view and (column.name in self.spec.user_readonly_columns or column.name == self.spec.owner)

    def describe(self) -> dict:
        return {
            "name": self.name,
            "label": self.spec.label or self.name,
            "pk": [c.name for c in self.pk],
            "mode": self.spec.mode,
            "columns": [
                {
                    "name": c.name,
                    "type": _kind(c),
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
        if self.user_view and "U" not in self.user_ops:
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
            raise _bad(f"Unknown column '{name}'")
        is_ref = name in self.refs
        if self.is_secret(col) or self.is_readonly(col) or (not is_ref and _kind(col) not in ("string", "text")):
            raise _bad(f"Column '{name}' takes no suggestions")
        term = q.strip()
        if not term:
            return {"values": [], "options": []} if is_ref else {"values": []}
        pattern = f"%{_escape_like(term)}%"
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
            raise _bad(f"Unknown column '{name}'")
        if self.is_secret(col) or _kind(col) not in ("string", "text"):
            raise _bad(f"Column '{name}' cannot be grouped by")
        count = func.count().label("n")
        stmt = select(col, count).where(col.is_not(None), col != "", *base).group_by(col).order_by(count.desc(), col).limit(limit)
        return {"values": [{"value": str(v), "count": n} for v, n in db.execute(stmt)]}

    def pk_clause(self, raw: str) -> list:
        parts = raw.split(PK_SEPARATOR)
        if len(parts) != len(self.pk):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        clause = []
        for column, part in zip(self.pk, parts):
            kind = _kind(column)
            try:
                value = _coerce(column.name, kind, int(part) if kind == "int" else part)
            except (HTTPException, ValueError):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None
            clause.append(column == value)
        return clause

    def pk_text(self, row: Any) -> str:
        return PK_SEPARATOR.join(str(row[c.name]) for c in self.pk)

    def clean_values(self, values: Any, *, creating: bool) -> dict[str, Any]:
        if not isinstance(values, dict):
            raise _bad("'values' must be an object")
        cleaned: dict[str, Any] = {}
        pk_names = {c.name for c in self.pk}
        for name, raw in values.items():
            column = self.by_name.get(name)
            if column is None:
                raise _bad(f"Unknown column '{name}'")
            if self.is_readonly(column) or self.is_secret(column) or (not creating and name in pk_names):
                raise _bad(f"Column '{name}' is not writable")
            if raw is None:
                if not column.nullable:
                    raise _bad(f"Column '{name}' must not be null")
                cleaned[name] = None
            else:
                cleaned[name] = _coerce(name, _kind(column), raw)
        if creating:
            for column in self.columns:
                if column.name in cleaned or self.is_readonly(column) or self.is_secret(column):
                    continue
                has_default = column.default is not None or column.server_default is not None
                auto = self.table._autoincrement_column is column
                if not column.nullable and not has_default and not auto:
                    raise _bad(f"Column '{column.name}' is required")
        return cleaned


BATCH_MAX = 200  # rows per batch request


def _db_error(exc: SQLAlchemyError, db: Session) -> HTTPException:
    db.rollback()
    if isinstance(exc, IntegrityError):
        return HTTPException(status.HTTP_409_CONFLICT, "Conflicts with an existing row or a constraint")
    if isinstance(exc, DataError):
        return _bad("A value is not accepted by the database")
    logger.exception("admincrud database error")
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Database error")


def _unknown_table() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Unknown table")


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


def _fetch_one(db: Session, admin: _Admin, clause: list) -> Any:
    row = db.execute(select(*admin.table.columns).where(*clause)).mappings().first()
    if row is None:
        raise _not_found()
    return row


FILTER_PREFIX = "filter_"


def _filters_of(request: Request) -> dict[str, str]:
    """The `filter_<column>=<value>` query parameters of a list request."""
    return {k[len(FILTER_PREFIX):]: v for k, v in request.query_params.items() if k.startswith(FILTER_PREFIX)}


def _filter_conditions(admin: _Admin, filters: dict[str, str]) -> list:
    conditions = []
    for name, raw in filters.items():
        col = admin.by_name.get(name)
        if col is None or admin.is_secret(col) or _kind(col) in ("json", "bytes"):
            raise _bad(f"Cannot filter on column '{name}'")
        conditions.append(col == _coerce(name, _kind(col), raw))
    return conditions


def _sort_order(admin: _Admin, sort: str | None) -> list:
    if not sort:
        return [c.desc() for c in admin.pk]
    name = sort.lstrip("-") if sort.startswith("-") else sort
    col = admin.by_name.get(name)
    if col is None or admin.is_secret(col) or _kind(col) in ("json", "bytes"):
        raise _bad(f"Cannot sort by column '{name}'")
    return [col.desc() if sort.startswith("-") else col.asc(), *admin.pk]


SHORT_TERM_LENGTH = 3  # a shorter term, or a number, matches whole words only ("2" finds "Bag 2", not "Bag 29")


def _terms(q: str) -> list[str]:
    """The search terms of `q`: the comma-separated parts (all must match); one part may be `column:value` for a single column."""
    return [part.strip() for part in q.split(",") if part.strip()]


def _list_rows(
    admin: _Admin, db: Session, q: str, offset: int, limit: int, base: list,
    sort: str | None = None, filters: dict[str, str] | None = None,
) -> dict:
    conditions = [*base, *_filter_conditions(admin, filters or {})]
    order = _sort_order(admin, sort)
    text_columns = [c for c in admin.columns if _kind(c) in ("string", "text") and not admin.is_secret(c)]
    for term in _terms(q):
        name, _, value = term.partition(":")
        column = next((c for c in text_columns if c.name == name.strip()), None) if value.strip() else None
        if column is not None:
            conditions.append(column.ilike(f"%{_escape_like(value.strip())}%", escape="\\"))
            continue
        if not text_columns:
            return {"total": 0, "rows": []}
        escaped = _escape_like(term)
        patterns = [f"%{escaped}%"] if not term.isalnum() or (len(term) >= SHORT_TERM_LENGTH and not term.isdigit()) else [escaped, f"{escaped} %", f"% {escaped}", f"% {escaped} %"]
        conditions.append(or_(*[c.ilike(pattern, escape="\\") for c in text_columns for pattern in patterns]))
    total = db.scalar(select(func.count()).select_from(admin.table).where(*conditions)) or 0
    rows = db.execute(select(*admin.table.columns).where(*conditions).order_by(*order).offset(offset).limit(limit))
    out = [admin.out(r) for r in rows.mappings()]
    return _with_labels({"total": total, "rows": out}, admin, db, out)


def _with_labels(payload: dict, admin: _Admin, db: Session, rows: list[dict]) -> dict:
    labels = admin.labels_for(db, rows) if admin.refs and rows else {}
    return {**payload, "labels": labels} if labels else payload


def _row_payload(admin: _Admin, db: Session, row: Any) -> dict:
    out = admin.out(row)
    return _with_labels(out, admin, db, [out])


def _insert_row(admin: _Admin, db: Session, values: dict) -> Any:
    try:
        result = db.execute(insert(admin.table).values(**values))
        clause = [c == v for c, v in zip(admin.pk, result.inserted_primary_key)]
        row = _fetch_one(db, admin, clause)
        db.commit()
    except SQLAlchemyError as exc:
        raise _db_error(exc, db) from None
    return row


def _update_row(admin: _Admin, db: Session, clause: list, values: dict) -> Any:
    try:
        if values:
            db.execute(update(admin.table).where(*clause).values(**values))
        db.commit()
        return _fetch_one(db, admin, clause)
    except SQLAlchemyError as exc:
        raise _db_error(exc, db) from None


def _delete_row(admin: _Admin, db: Session, request: Request, user: TokenPayload, clause: list, row: Any) -> None:
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
        raise _db_error(exc, db) from None
    if after_commit is not None:
        after_commit()


def admin_router(models: list[TableSpec], *, get_db_dep: Callable = get_db) -> APIRouter:
    tables = {spec.table.name: _Admin(spec) for spec in models}
    router = APIRouter(tags=["admin"], dependencies=[*access_dependencies(admin=True, moderator=True, user=True), Depends(check_origin)])

    def find(name: str) -> _Admin:
        admin = tables.get(name)
        if admin is None:
            raise _unknown_table()
        return admin

    def writable(admin: _Admin, creating: bool = False) -> None:
        if admin.spec.mode != "crud" and (creating or admin.spec.mode != "edit-delete"):
            raise HTTPException(status.HTTP_405_METHOD_NOT_ALLOWED, "Table is not editable")

    def audit(user: TokenPayload, action: str, admin: _Admin, pk: str) -> None:
        logger.info("admin %s user_id=%s table=%s pk=%s", action, user.user_id, admin.name, pk)

    @router.get("/tables")
    def list_tables() -> list[dict]:
        return [admin.describe() for admin in tables.values()]

    @router.get("/{table}")
    def list_rows(
        request: Request,
        table: str,
        q: str = "",
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=MAX_LIMIT),
        sort: str | None = None,
        db: Session = Depends(get_db_dep),
    ) -> dict:
        return _list_rows(find(table), db, q, offset, limit, [], sort, _filters_of(request))

    @router.get("/{table}/suggest")
    def suggest(
        table: str,
        column: str,
        q: str = "",
        limit: int = Query(10, ge=1, le=SUGGEST_MAX),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        return find(table).suggest(db, column, q, limit, [])

    @router.get("/{table}/groups")
    def groups(table: str, column: str, limit: int = Query(GROUPS_MAX, ge=1, le=GROUPS_MAX), db: Session = Depends(get_db_dep)) -> dict:
        return find(table).groups(db, column, limit, [])

    @router.get("/{table}/{pk}")
    def get_row(table: str, pk: str, db: Session = Depends(get_db_dep)) -> dict:
        admin = find(table)
        return _row_payload(admin, db, _fetch_one(db, admin, admin.pk_clause(pk)))

    @router.post("/{table}", status_code=status.HTTP_201_CREATED)
    def create_row(
        table: str,
        body: dict = Body(...),
        user: TokenPayload = Depends(get_current_user),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        admin = find(table)
        writable(admin, creating=True)
        values = admin.clean_values(body.get("values", {}), creating=True)
        row = _insert_row(admin, db, values)
        audit(user, "create", admin, admin.pk_text(row))
        return admin.out(row)

    def _excel_rows(data: bytes) -> list[dict]:
        try:
            return recordfiles.read_excel(data, BATCH_MAX)
        except recordfiles.FileRefused as exc:
            raise _bad(str(exc)) from None

    def _key_of(admin: _Admin, values: dict) -> Any:
        """The key of a row of the Excel file (its `id`), or None when the file names none."""
        pk_names = [c.name for c in admin.pk]
        if len(pk_names) != 1 or pk_names[0] not in values or values[pk_names[0]] in (None, ""):
            return None
        return values[pk_names[0]]

    def plan_import(table: str, data: bytes, db: Session) -> dict:
        """What an import would do, row by row: whether its id is already in the table (then the person chooses to overwrite it or not)."""
        admin = find(table)
        rows = _excel_rows(data)
        pk_column = admin.pk[0] if len(admin.pk) == 1 else None
        plan = []
        for index, values in enumerate(rows):
            key = _key_of(admin, values)
            exists = key is not None and pk_column is not None and db.execute(select(pk_column).where(pk_column == key)).first() is not None
            plan.append({"index": index, "id": key, "exists": bool(exists)})
        return {"rows": plan, "new": sum(1 for r in plan if not r["exists"]), "existing": sum(1 for r in plan if r["exists"]), "data": rows}

    def apply_import(table: str, rows: list[dict], overwrite: bool, user: TokenPayload, db: Session) -> dict:
        """Creates the rows of an import. A row whose id is in the table is overwritten only when `overwrite` is set; otherwise skipped."""
        admin = find(table)
        pk_column = admin.pk[0] if len(admin.pk) == 1 else None
        results = []
        for index, values in enumerate(rows):
            try:
                key = _key_of(admin, values)
                exists = key is not None and pk_column is not None and db.execute(select(pk_column).where(pk_column == key)).first() is not None
                if exists and not overwrite:
                    results.append({"index": index, "status": "skipped", "id": key})
                    continue
                if exists:
                    rest = {k: v for k, v in values.items() if k not in {c.name for c in admin.pk}}
                    clause = admin.pk_clause(str(key))
                    _update_row(admin, db, clause, admin.clean_values(rest, creating=False))
                    audit(user, "update", admin, str(key))
                    results.append({"index": index, "status": "updated", "id": key})
                else:
                    row = _insert_row(admin, db, admin.clean_values(values, creating=True))
                    audit(user, "create", admin, admin.pk_text(row))
                    results.append({"index": index, "status": "created", "id": key if key is not None else admin.pk_text(row)})
            except HTTPException as exc:
                db.rollback()
                results.append({"index": index, "status": "error", "error": str(exc.detail)})
        return {"results": results, "created": sum(1 for r in results if r["status"] == "created"), "updated": sum(1 for r in results if r["status"] == "updated"), "skipped": sum(1 for r in results if r["status"] == "skipped")}

    @router.post("/{table}/batch")
    def create_rows(
        table: str,
        body: dict = Body(...),
        user: TokenPayload = Depends(get_current_user),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        """Create many rows at once. Each row is checked and saved on its own: a bad row does not stop the others."""
        admin = find(table)
        writable(admin, creating=True)
        rows = body.get("rows")
        if not isinstance(rows, list) or not rows:
            raise _bad("'rows' must be a non-empty list")
        if len(rows) > BATCH_MAX:
            raise _bad(f"At most {BATCH_MAX} rows per request")
        results = []
        for index, item in enumerate(rows):
            try:
                values = admin.clean_values(item.get("values", item) if isinstance(item, dict) else item, creating=True)
                row = _insert_row(admin, db, values)
                audit(user, "create", admin, admin.pk_text(row))
                results.append({"index": index, "ok": True, "row": admin.out(row)})
            except HTTPException as exc:
                db.rollback()
                results.append({"index": index, "ok": False, "error": str(exc.detail)})
        return {"results": results, "created": sum(1 for r in results if r["ok"])}

    @router.post("/{table}/batch-update")
    def update_rows(
        table: str,
        body: dict = Body(...),
        user: TokenPayload = Depends(get_current_user),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        """Change many rows at once (the Database tab's sheet): `rows` = [{pk, values}], each row checked and saved on its own."""
        admin = find(table)
        writable(admin)
        rows = body.get("rows")
        if not isinstance(rows, list) or not rows:
            raise _bad("'rows' must be a non-empty list")
        if len(rows) > BATCH_MAX:
            raise _bad(f"At most {BATCH_MAX} rows per request")
        results = []
        for index, item in enumerate(rows):
            try:
                pk = str(item["pk"])
                values = admin.clean_values(item.get("values", {}), creating=False)
                clause = admin.pk_clause(pk)
                _fetch_one(db, admin, clause)
                _update_row(admin, db, clause, values)
                audit(user, "update", admin, pk)
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
        table: str,
        pk: str,
        body: dict = Body(...),
        user: TokenPayload = Depends(get_current_user),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        admin = find(table)
        writable(admin)
        clause = admin.pk_clause(pk)
        values = admin.clean_values(body.get("values", {}), creating=False)
        _fetch_one(db, admin, clause)
        row = _update_row(admin, db, clause, values)
        audit(user, "update", admin, pk)
        return admin.out(row)

    @router.delete("/{table}/{pk}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_row(
        table: str,
        pk: str,
        request: Request,
        user: TokenPayload = Depends(get_current_user),
        db: Session = Depends(get_db_dep),
    ) -> Response:
        admin = find(table)
        clause = admin.pk_clause(pk)
        row = _fetch_one(db, admin, clause)
        _delete_row(admin, db, request, user, clause, row)
        audit(user, "delete", admin, pk)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    router.handlers = SimpleNamespace(list_tables=list_tables, list_rows=list_rows, suggest=suggest, groups=groups, get_row=get_row, create_row=create_row, create_rows=create_rows, update_rows=update_rows, plan_import=plan_import, apply_import=apply_import, patch_row=patch_row, delete_row=delete_row)  # type: ignore[attr-defined]
    return router


def data_router(
    models: list[TableSpec], *, get_db_dep: Callable = get_db, get_user_dep: Callable = get_current_user
) -> APIRouter:
    """The user-facing, owner-scoped twin of admin_router (mount at "/data"): same contract, per signed-in person."""
    tables = {spec.table.name: _Admin(spec, user_view=True) for spec in models if spec.user_ops}
    router = APIRouter(tags=["data"], dependencies=[*access_dependencies(admin=True, moderator=True, user=True), Depends(check_origin)])

    def find(name: str) -> _Admin:
        admin = tables.get(name)
        if admin is None:
            raise _unknown_table()
        return admin

    def allow(admin: _Admin, op: str) -> None:
        if op not in admin.user_ops:
            raise HTTPException(status.HTTP_405_METHOD_NOT_ALLOWED, "Operation not allowed on this table")

    def visible(admin: _Admin, db: Session, user: TokenPayload) -> list:
        if admin.spec.scope is not None:
            return [admin.spec.scope(db, user)]
        return [admin.table.c[admin.spec.owner] == user.user_id]

    def mine(admin: _Admin, user: TokenPayload) -> list:
        return [admin.table.c[admin.spec.owner] == user.user_id]

    def audit(user: TokenPayload, action: str, admin: _Admin, pk: str) -> None:
        logger.info("data %s user_id=%s table=%s pk=%s", action, user.user_id, admin.name, pk)

    @router.get("/tables")
    def list_tables() -> list[dict]:
        return [{**admin.describe(), "ops": admin.user_ops} for admin in tables.values()]

    @router.get("/{table}")
    def list_rows(
        request: Request,
        table: str,
        q: str = "",
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=MAX_LIMIT),
        sort: str | None = None,
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        admin = find(table)
        allow(admin, "R")
        return _list_rows(admin, db, q, offset, limit, visible(admin, db, user), sort, _filters_of(request))

    @router.get("/{table}/suggest")
    def suggest(
        table: str,
        column: str,
        q: str = "",
        limit: int = Query(10, ge=1, le=SUGGEST_MAX),
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        admin = find(table)
        allow(admin, "R")
        return admin.suggest(db, column, q, limit, visible(admin, db, user))

    @router.get("/{table}/groups")
    def groups(
        table: str,
        column: str,
        limit: int = Query(GROUPS_MAX, ge=1, le=GROUPS_MAX),
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        admin = find(table)
        allow(admin, "R")
        return admin.groups(db, column, limit, visible(admin, db, user))

    @router.get("/{table}/{pk}")
    def get_row(
        table: str, pk: str, user: TokenPayload = Depends(get_user_dep), db: Session = Depends(get_db_dep)
    ) -> dict:
        admin = find(table)
        allow(admin, "R")
        return _row_payload(admin, db, _fetch_one(db, admin, [*admin.pk_clause(pk), *visible(admin, db, user)]))

    @router.post("/{table}", status_code=status.HTTP_201_CREATED)
    def create_row(
        table: str,
        body: dict = Body(...),
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        admin = find(table)
        allow(admin, "C")
        raw = body.get("values", {})
        if not isinstance(raw, dict):
            raise _bad("'values' must be an object")
        owner = admin.spec.owner
        if owner in raw and raw[owner] is not None and str(raw[owner]) != str(user.user_id):
            raise _bad(f"Column '{owner}' is not writable")
        values = admin.clean_values({k: v for k, v in raw.items() if k != owner}, creating=True)
        row = _insert_row(admin, db, {**values, owner: user.user_id})
        audit(user, "create", admin, admin.pk_text(row))
        return admin.out(row)

    @router.patch("/{table}/{pk}")
    def patch_row(
        table: str,
        pk: str,
        body: dict = Body(...),
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        admin = find(table)
        allow(admin, "U")
        clause = [*admin.pk_clause(pk), *mine(admin, user)]
        values = admin.clean_values(body.get("values", {}), creating=False)
        _fetch_one(db, admin, clause)
        row = _update_row(admin, db, clause, values)
        audit(user, "update", admin, pk)
        return admin.out(row)

    @router.delete("/{table}/{pk}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_row(
        table: str,
        pk: str,
        request: Request,
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> Response:
        admin = find(table)
        allow(admin, "D")
        clause = [*admin.pk_clause(pk), *mine(admin, user)]
        row = _fetch_one(db, admin, clause)
        _delete_row(admin, db, request, user, clause, row)
        audit(user, "delete", admin, pk)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    router.handlers = SimpleNamespace(list_tables=list_tables, list_rows=list_rows, suggest=suggest, groups=groups, get_row=get_row, create_row=create_row, patch_row=patch_row, delete_row=delete_row)  # type: ignore[attr-defined]
    return router


def _remove_file(relative: str) -> None:
    try:
        recordfiles.location(relative).unlink(missing_ok=True)
    except (OSError, recordfiles.FileRefused):
        logger.warning("could not remove the old file %s", relative)


def records_router(
    models: list[TableSpec], *, get_db_dep: Callable = get_db, get_user_dep: Callable = get_current_user, database: str = "app"
) -> APIRouter:
    """One address for everyone (mount at "/records"): the same contract as `admin_router` and `data_router`, and the role decides what it does.

    `?scope=all` is the admin's view (every row, as far as the table's `mode` lets); `?scope=mine` is the person's own rows (as far as
    `user_ops` lets, with the columns a person may see). With no `scope` an admin gets `all` and anyone else `mine`; `all` from anyone else is
    refused. Nothing is decided here: each call is handed to the handler of the router that already does it, so the rules stay in one place.
    """
    admin = admin_router(models, get_db_dep=get_db_dep).handlers  # type: ignore[attr-defined]
    data = data_router(models, get_db_dep=get_db_dep, get_user_dep=get_user_dep).handlers  # type: ignore[attr-defined]
    router = APIRouter(tags=["records"], dependencies=[*access_dependencies(admin=True, moderator=True, user=True), Depends(check_origin)])

    def everyone(user: TokenPayload, scope: str | None) -> bool:
        wanted = scope or ("all" if user.group == GROUP_ADMIN else "mine")
        if wanted not in ("all", "mine"):
            raise _bad("'scope' must be 'all' or 'mine'")
        if wanted == "all" and user.group != GROUP_ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin may ask for every row")
        return wanted == "all"

    @router.get("/tables")
    def list_tables(scope: str | None = None, user: TokenPayload = Depends(get_user_dep)) -> list[dict]:
        return admin.list_tables() if everyone(user, scope) else data.list_tables()

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
        if everyone(user, scope):
            return admin.list_rows(request, table, q, offset, limit, sort, db)
        return data.list_rows(request, table, q, offset, limit, sort, user, db)

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
        if everyone(user, scope):
            return admin.suggest(table, column, q, limit, db)
        return data.suggest(table, column, q, limit, user, db)

    @router.get("/{table}/groups")
    def groups(
        table: str,
        column: str,
        limit: int = Query(GROUPS_MAX, ge=1, le=GROUPS_MAX),
        scope: str | None = None,
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        if everyone(user, scope):
            return admin.groups(table, column, limit, db)
        return data.groups(table, column, limit, user, db)

    @router.get("/{table}/{pk}")
    def get_row(table: str, pk: str, scope: str | None = None, user: TokenPayload = Depends(get_user_dep), db: Session = Depends(get_db_dep)) -> dict:
        if everyone(user, scope):
            return admin.get_row(table, pk, db)
        return data.get_row(table, pk, user, db)

    @router.post("/{table}/import-plan")
    async def import_plan(
        table: str,
        file: UploadFile = File(...),
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        """What importing this Excel file would do: how many of its rows are new and how many have an id already in the table (admin only)."""
        if user.group != GROUP_ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin may import rows")
        _excel_file(table, file)
        plan = admin.plan_import(table, await file.read(), db)
        return {"rows": plan["rows"], "new": plan["new"], "existing": plan["existing"]}

    @router.post("/{table}/import")
    async def import_rows(
        table: str,
        file: UploadFile = File(...),
        overwrite: bool = Form(False),
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        """Imports the rows of an Excel file (admin only). A row whose id is already in the table is overwritten only when `overwrite`
        is set, else it is skipped: the rows that are not there yet are always created."""
        if user.group != GROUP_ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin may import rows")
        _excel_file(table, file)
        plan = admin.plan_import(table, await file.read(), db)
        return admin.apply_import(table, plan["data"], overwrite, user, db)

    def _excel_file(table: str, file: UploadFile) -> None:
        if not any(spec.model.__tablename__ == table for spec in models):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown table")
        if os.path.splitext(file.filename or "")[1].lower() not in recordfiles.EXCEL_EXTENSIONS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only .xlsx files can be imported")

    def _media_column(table: str, column: str) -> tuple[Any, str]:
        spec = next((spec for spec in models if spec.model.__tablename__ == table), None)
        if spec is None or column not in spec.media:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a file column")
        return spec, str(spec.media[column].get("kind", "image"))

    @router.post("/{table}/{pk}/files/{column}")
    async def upload_file(
        table: str,
        pk: str,
        column: str,
        file: UploadFile = File(...),
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        """Add a file to a picture, audio, video or file cell of a row (an admin only). All the files of a cell share one folder:
        `{database}/{table}/{column}/{row_id}/`. A file with the same name replaces the one there."""
        if user.group != GROUP_ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin may upload files here")
        _, kind = _media_column(table, column)
        data = await file.read()
        try:
            name = recordfiles.check(kind, file.filename or "", len(data))
            folder = recordfiles.folder_of(database, table, column, pk)
            recordfiles.save(f"{folder}/{name}", data)
        except recordfiles.FileRefused as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
        if admin.get_row(table, pk, db).get(column) != folder:
            return admin.patch_row(table, pk, {"values": {column: folder}}, user, db)
        return admin.get_row(table, pk, db)

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
        _media_column(table, column)
        row = get_row(table, pk, scope, user, db)
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
        _media_column(table, column)
        row = get_row(table, pk, scope, user, db)
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
        """Remove one file of a cell (an admin only)."""
        if user.group != GROUP_ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin may remove files here")
        _media_column(table, column)
        row = admin.get_row(table, pk, db)
        held = {entry.rsplit("/", 1)[-1]: entry for entry in recordfiles.files_of(str(row.get(column) or ""))}
        if name not in held:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such file here")
        recordfiles.remove(held[name])
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/{table}/batch")
    def create_rows(
        table: str,
        body: dict = Body(...),
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        """Bulk entry (Database tab, "Quick entry"): an admin only, row by row, the same rules as the admin batch."""
        if user.group != GROUP_ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin may enter rows in bulk")
        return admin.create_rows(table, body, user, db)

    @router.post("/{table}/batch-update")
    def update_rows(
        table: str,
        body: dict = Body(...),
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> dict:
        """Change many rows at once (the Database tab's sheet): an admin only, the same rules as the admin batch."""
        if user.group != GROUP_ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin may change rows in bulk")
        return admin.update_rows(table, body, user, db)

    @router.post("/{table}", status_code=status.HTTP_201_CREATED)
    def create_row(
        table: str, body: dict = Body(...), scope: str | None = None, user: TokenPayload = Depends(get_user_dep), db: Session = Depends(get_db_dep)
    ) -> dict:
        if everyone(user, scope):
            return admin.create_row(table, body, user, db)
        return data.create_row(table, body, user, db)

    @router.patch("/{table}/{pk}")
    def patch_row(
        table: str, pk: str, body: dict = Body(...), scope: str | None = None, user: TokenPayload = Depends(get_user_dep), db: Session = Depends(get_db_dep)
    ) -> dict:
        if everyone(user, scope):
            return admin.patch_row(table, pk, body, user, db)
        return data.patch_row(table, pk, body, user, db)

    @router.delete("/{table}/{pk}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_row(
        table: str,
        pk: str,
        request: Request,
        scope: str | None = None,
        user: TokenPayload = Depends(get_user_dep),
        db: Session = Depends(get_db_dep),
    ) -> Response:
        if everyone(user, scope):
            return admin.delete_row(table, pk, request, user, db)
        return data.delete_row(table, pk, request, user, db)

    return router


def mount_crud(app: Any, models: list[TableSpec], *, database: str = "app") -> None:
    """Mounts a module's tables at `/records` only: admins see every row, anyone else their own (`scope` may ask for either).
    `database` names the folder of the module's files (`{database}/{table}/{column}/{row_id}/{file}`)."""
    app.include_router(records_router(models, database=database), prefix="/records")
