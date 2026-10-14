"""File manager: one sandbox directory per user, virtual paths only (see app/paths.py)."""

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app import store
from app.deps import writer
from app.paths import MAX_DEPTH, NotFound, PathError, Resolved, resolve, validate_name
from app.security import check_origin
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

MAX_FILE_BYTES = 20 * 1024 * 1024
QUOTA_BYTES = 100 * 1024 * 1024
MAX_LIST_ENTRIES = 500
MAX_NODES_PER_USER = 1000
MAX_DELETE_ENTRIES = 2000
CHUNK = 64 * 1024

router = APIRouter(dependencies=[Depends(check_origin)])
VirtualPath = Annotated[str, Query(max_length=700)]


class FolderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(max_length=700)
    name: str = Field(max_length=300)


class RenameIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    path: str = Field(max_length=700)
    new_name: str = Field(alias="newName", max_length=300)


def _ensure_root(user_id: int) -> Path:
    root = store.files_root(user_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _scan(root: Path) -> tuple[int, int]:
    """(bytes, nodes) of a tree; symlinks count as nodes but are never followed."""
    total = nodes = 0
    for current, dirs, names in os.walk(root, followlinks=False):
        nodes += len(dirs) + len(names)
        for name in names:
            try:
                total += os.lstat(os.path.join(current, name)).st_size
            except OSError:
                continue
    return total, nodes


def _resolve(root: Path, raw: str) -> Resolved:
    try:
        return resolve(root, raw)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy tệp hoặc thư mục") from None
    except PathError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None


def _name(raw: str) -> str:
    try:
        return validate_name(raw)
    except PathError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None


def _directory(root: Path, raw: str) -> Resolved:
    target = _resolve(root, raw)
    if not target.real.is_dir():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Đường dẫn không phải thư mục")
    return target


def _check_new_entry(root: Path, parent: Resolved, name: str) -> Path:
    """The real path a new child `name` of `parent` would get, after depth / collision / count limits."""
    if len(parent.parts) + 1 > MAX_DEPTH:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Đường dẫn quá sâu (tối đa 6 cấp)")
    target = parent.real / name
    if os.path.lexists(target):
        raise HTTPException(status.HTTP_409_CONFLICT, "Tên này đã tồn tại")
    with os.scandir(parent.real) as entries:
        count = sum(1 for _ in entries)
    if count >= MAX_LIST_ENTRIES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Thư mục đã đầy (tối đa 500 mục)")
    if _scan(root)[1] >= MAX_NODES_PER_USER:
        raise HTTPException(status.HTTP_409_CONFLICT, "Đã đạt số tệp và thư mục tối đa (1000)")
    return target


def _entry(entry: os.DirEntry) -> dict | None:
    try:
        if entry.is_symlink():
            return None
        info = entry.stat(follow_symlinks=False)
        is_dir = entry.is_dir(follow_symlinks=False)
    except OSError:  # pragma: no cover - vanished during the scan
        return None
    return {
        "name": entry.name,
        "type": "folder" if is_dir else "file",
        "size": 0 if is_dir else info.st_size,
        "modifiedAt": int(info.st_mtime),
    }


@router.get("/files")
def list_files(path: VirtualPath = "/", user: TokenPayload = Depends(get_current_user)) -> dict:
    root = _ensure_root(user.user_id)
    target = _directory(root, path)
    with os.scandir(target.real) as scan:
        entries = [item for item in map(_entry, scan) if item is not None]
    entries.sort(key=lambda e: (e["type"] != "folder", e["name"].casefold(), e["name"]))
    return {
        "path": target.virtual,
        "entries": entries[:MAX_LIST_ENTRIES],
        "usage": {"usedBytes": _scan(root)[0], "quotaBytes": QUOTA_BYTES},
    }


@router.post("/files/folder", status_code=status.HTTP_201_CREATED)
def create_folder(body: FolderIn, user: TokenPayload = Depends(writer)) -> dict:
    name = _name(body.name)
    root = _ensure_root(user.user_id)
    with store.user_lock(user.user_id):
        parent = _directory(root, body.path)
        os.mkdir(_check_new_entry(root, parent, name))
    return {"name": name}


def _spool(source, limit: int) -> tuple[Path, int]:
    """Copy the upload to a temp file on the data volume (same filesystem as the target: atomic rename)."""
    incoming = store.incoming_dir()
    incoming.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=incoming, prefix="up-")
    size = 0
    try:
        with os.fdopen(handle, "wb") as out:
            while chunk := source.read(CHUNK):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, "Tệp lớn hơn 20 MB")
                out.write(chunk)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return Path(temp), size


@router.post("/files/upload", status_code=status.HTTP_201_CREATED)
def upload(
    file: Annotated[UploadFile, File()],
    path: VirtualPath = "/",
    user: TokenPayload = Depends(writer),
) -> dict:
    name = _name(re.split(r"[\\/]", file.filename or "")[-1])  # a client may send a path: keep the last part
    root = _ensure_root(user.user_id)
    with store.user_lock(user.user_id):
        parent = _directory(root, path)
        target = _check_new_entry(root, parent, name)
        used = _scan(root)[0]
        temp, size = _spool(file.file, MAX_FILE_BYTES)
        try:
            if used + size > QUOTA_BYTES:
                raise HTTPException(413, "Vượt quá dung lượng 100 MB")
            os.replace(temp, target)  # atomic; the collision check and the user lock rule out an overwrite
        finally:
            temp.unlink(missing_ok=True)
    return {"name": name, "size": size}


@router.get("/files/download")
def download(path: VirtualPath, user: TokenPayload = Depends(get_current_user)) -> FileResponse:
    root = _ensure_root(user.user_id)
    target = _resolve(root, path)
    if not target.parts or not target.real.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy tệp")
    return FileResponse(
        target.real,
        media_type="application/octet-stream",
        filename=target.parts[-1],
        content_disposition_type="attachment",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/files", status_code=status.HTTP_204_NO_CONTENT)
def delete(path: VirtualPath, user: TokenPayload = Depends(writer)) -> Response:
    root = _ensure_root(user.user_id)
    with store.user_lock(user.user_id):
        target = _resolve(root, path)
        if not target.parts:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể xóa thư mục gốc")
        if target.real.is_dir():
            if _scan(target.real)[1] > MAX_DELETE_ENTRIES:
                raise HTTPException(status.HTTP_409_CONFLICT, "Thư mục có quá nhiều mục để xóa cùng lúc")
            shutil.rmtree(target.real)
        else:
            target.real.unlink()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/files/rename")
def rename(body: RenameIn, user: TokenPayload = Depends(writer)) -> dict:
    new_name = _name(body.new_name)
    root = _ensure_root(user.user_id)
    with store.user_lock(user.user_id):
        target = _resolve(root, body.path)
        if not target.parts:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể đổi tên thư mục gốc")
        if new_name != target.parts[-1]:
            destination = target.real.parent / new_name
            if os.path.lexists(destination):
                raise HTTPException(status.HTTP_409_CONFLICT, "Tên này đã tồn tại")
            os.rename(target.real, destination)
    return {"name": new_name}
