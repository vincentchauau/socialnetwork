"""A reusable `PUT <path>` route that replaces the file behind a row (an image, a video, any upload).

    add_replace_route(app, "/photos/{item_id}/image", model=Photo, get_db=get_db, get_user=get_current_user,
                      inspect=inspect_image, write=save_file, delete=remove_files, ref_columns=("image_name",),
                      respond=lambda db, row, user: to_out(db, [row], user)[0])

The route takes a multipart `file`. The row's owner (column `owner`) or an admin may replace it; anybody else gets 404
(the row's existence is not revealed). `inspect(raw, file)` validates the bytes and returns `Inspected(data, updates)`
(raise `MediaRejected(status, detail)` to refuse); `write(row, data, updates)` stores the new file and returns the
columns that point to it. The old files go (`delete(old_columns)`) after the commit; the new ones go if the commit fails.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Path, UploadFile, status
from sqlalchemy.orm import Session

from sn_shared.security import TokenPayload

import logging
logger = logging.getLogger(__name__)

MAX_ID = 2**63 - 1
DEFAULT_MAX_BYTES = 5 * 1024 * 1024


class MediaRejected(Exception):
    """The upload is refused: `status_code` and `detail` go to the caller."""

    def __init__(self, status_code: int, detail: str) -> None:
        try:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise


@dataclass(frozen=True)
class Inspected:
    data: bytes  # what is stored (an image may have been re-encoded)
    updates: dict[str, Any] = field(default_factory=dict)  # columns to set from the content (content_type, width, size...)


def add_replace_route(
    target: FastAPI | APIRouter,
    path: str,
    *,
    model: Any,
    get_db: Callable,
    get_user: Callable,
    inspect: Callable[[bytes, UploadFile], Inspected],
    write: Callable[[Any, bytes, dict[str, Any]], dict[str, Any]],
    delete: Callable[[dict[str, Any]], None],
    ref_columns: Sequence[str],
    respond: Callable[[Session, Any, TokenPayload], Any],
    owner: str = "user_id",
    max_bytes: int = DEFAULT_MAX_BYTES,
    allowed_types: Sequence[str] | None = None,
    response_model: Any = None,
    tags: list[str] | None = None,
) -> None:
    """Add `PUT <path>` (which must hold the `{item_id}` placeholder) to an app or router.

    `allowed_types` (content types, `image/*` style prefixes allowed) is checked on the declared type when given and
    the declared type is not the generic octet-stream; `inspect` is the real check. 413 over `max_bytes`.
    """

    try:
        def type_ok(declared: str | None) -> bool:
            try:
                if not allowed_types or not declared or declared == "application/octet-stream":
                    return True
                return any(declared == t or (t.endswith("/*") and declared.startswith(t[:-1])) for t in allowed_types)
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("type_ok failed")
                raise

        def replace(
            file: UploadFile = File(),
            item_id: int = Path(ge=1, le=MAX_ID),
            user: TokenPayload = Depends(get_user),
            db: Session = Depends(get_db),
        ) -> Any:
            row = db.get(model, item_id)
            if row is None or (getattr(row, owner) != user.user_id and user.group != "admin"):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
            if not type_ok(file.content_type):
                raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "This file type is not accepted")
            raw = file.file.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"The file is larger than {max_bytes // (1024 * 1024) or 1} MB")
            try:
                inspected = inspect(raw, file)
            except MediaRejected as error:
                raise HTTPException(error.status_code, error.detail) from None
            old = {name: getattr(row, name) for name in ref_columns}
            new = write(row, inspected.data, inspected.updates)
            try:
                for name, value in {**inspected.updates, **new}.items():
                    setattr(row, name, value)
                db.commit()
            except Exception:
                db.rollback()
                delete(new)
                raise
            if any(old[name] != new.get(name, old[name]) for name in old):
                delete(old)
            return respond(db, row, user)

        target.add_api_route(path, replace, methods=["PUT"], response_model=response_model, tags=tags)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("add_replace_route failed")
        raise
