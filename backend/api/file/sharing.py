"""Giving a file by a link: the owner makes, lists and takes back links; anybody with a link sees what the file is and downloads it."""

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from api.file import shares, store
from api.file.paths import PathError, NotFound, resolve
from sn_shared.deps import get_current_user
from sn_shared.limits import writer
from sn_shared.origin import check_origin
from sn_shared.security import TokenPayload

SEARCH_LIMIT = 100
router = APIRouter()
Token = Annotated[str, PathParam(min_length=16, max_length=64)]


class ShareIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(max_length=700)
    days: int | None = Field(default=None, ge=1, le=shares.MAX_DAYS)


def _file_of(user_id: int, path: str):
    """The file a link of `user_id` points at, or None when it is gone (or has become a folder)."""
    try:
        target = resolve(store.files_root(user_id), path)
    except (PathError, NotFound):
        return None
    return target if target.parts and target.real.is_file() else None


def _out(record: dict, size: int | None = None) -> dict:
    return {
        "token": record["token"], "path": record["path"], "page": shares.PAGE_PATH + record["token"], "createdAt": int(record["createdAt"]),
        "expiresAt": int(record["expiresAt"]) if record.get("expiresAt") else None, **({"size": size} if size is not None else {}),
    }


@router.post("/share", status_code=status.HTTP_201_CREATED, dependencies=[Depends(check_origin)])
def make_share(body: ShareIn, user: TokenPayload = Depends(writer)) -> dict:
    """A link that gives one of the person's files to whoever has it; the file's earlier link stops working."""
    with store.user_lock(user.user_id):
        target = _file_of(user.user_id, body.path)
        if target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy tệp")
        held = shares.mine(user.user_id)
        if len(held) >= shares.MAX_SHARES_PER_USER and not any(item["path"] == target.virtual for item in held):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Chỉ chia sẻ được tối đa {shares.MAX_SHARES_PER_USER} tệp")
        return _out(shares.make(user.user_id, target.virtual, body.days), target.real.stat().st_size)


@router.get("/shares")
def list_shares(user: TokenPayload = Depends(get_current_user)) -> dict:
    """The links of the person whose file is still there."""
    out = []
    for record in shares.mine(user.user_id):
        target = _file_of(user.user_id, record["path"])
        if target is not None:
            out.append(_out(record, target.real.stat().st_size))
    return {"shares": out}


@router.delete("/share/{token}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(check_origin)])
def take_back(token: Token, user: TokenPayload = Depends(writer)) -> Response:
    if not shares.drop(user.user_id, token):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy liên kết")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _shared_file(token: str):
    record = shares.find(token)
    target = _file_of(record["user_id"], record["path"]) if record else None
    if record is None or target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Liên kết này không còn dùng được")
    return record, target


@router.get("/shared/{token}")
def shared_info(token: Token) -> dict:
    """What the file behind a link is: open to anybody who has the link."""
    _, target = _shared_file(token)
    info = target.real.stat()
    return {"name": target.parts[-1], "size": info.st_size, "modifiedAt": int(info.st_mtime), "download": f"/shared/{token}/download"}


@router.get("/shared/{token}/download")
def shared_download(token: Token) -> FileResponse:
    _, target = _shared_file(token)
    return FileResponse(
        target.real,
        media_type="application/octet-stream",
        filename=target.parts[-1],
        content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox", "Cache-Control": "private, no-store"},
    )


@router.get("/search")
def search(q: Annotated[str, Query(min_length=2, max_length=100)], user: TokenPayload = Depends(get_current_user)) -> dict:
    """Files and folders of the person whose name holds `q` (any letter case), in every folder; the first 100."""
    root = store.files_root(user.user_id)
    words = q.strip().casefold()
    found: list[dict] = []
    if len(words) >= 2 and root.is_dir():
        for current, folders, names in os.walk(root, followlinks=False):
            folders.sort()
            here = Path(current).relative_to(root).as_posix()
            parent = "/" if here == "." else "/" + here
            for kind, group in (("folder", folders), ("file", sorted(names))):
                for name in group:
                    if words in name.casefold():
                        full = Path(current) / name
                        found.append({"name": name, "parent": parent, "type": kind, "size": 0 if kind == "folder" else full.lstat().st_size})
                        if len(found) >= SEARCH_LIMIT:
                            return {"entries": found, "more": True}
    return {"entries": found, "more": False}

