"""File manager: one sandbox directory per user, virtual paths only (see app/paths.py).

An admin has a second area, `data`: the whole data directory of the backend (the files of every app), with the same virtual paths and no
quota. What is there is shared by everybody, so only an admin goes in, and the folders at the top of it (the volumes) are never removed or renamed.
"""

import os
import re
import secrets
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from api.file import store, trash, versions
from sn_shared.limits import writer
from api.file.paths import MAX_DEPTH, MAX_NAME_LENGTH, NotFound, PathError, Resolved, resolve, to_virtual, validate_name
from sn_shared.origin import check_origin
from sn_shared.deps import GROUP_ADMIN, ensure_group, get_current_user
from sn_shared.security import TokenPayload

MAX_FILE_BYTES = 20 * 1024 * 1024
QUOTA_BYTES = 100 * 1024 * 1024
MAX_LIST_ENTRIES = 500
MAX_NODES_PER_USER = 1000
MAX_DELETE_ENTRIES = 2000
DATA_MAX_LIST_ENTRIES = 5000
DATA_MAX_DELETE_ENTRIES = 20000
DEFAULT_DATA_ROOT = "/data"
CHUNK = 64 * 1024

router = APIRouter(dependencies=[Depends(check_origin)])
VirtualPath = Annotated[str, Query(max_length=700)]
Area = Annotated[Literal["mine", "data"], Query()]


class FolderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(max_length=700)
    name: str = Field(max_length=300)


class MoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(max_length=700)
    to_folder: str = Field(alias="toFolder", max_length=700)


class RenameIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    path: str = Field(max_length=700)
    new_name: str = Field(alias="newName", max_length=300)


def ensure_root(user_id: int) -> Path:
    root = store.files_root(user_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def data_root() -> Path:
    return Path(os.environ.get("DATA_ROOT", DEFAULT_DATA_ROOT))


def _area(user: TokenPayload, area: str) -> tuple[Path, bool]:
    """(the root of the area, whether the limits of one person's sandbox hold in it)."""
    if area == "mine":
        return ensure_root(user.user_id), True
    ensure_group(user, GROUP_ADMIN, detail="Chỉ quản trị viên được quản lý thư mục dữ liệu của máy chủ")
    root = data_root()
    if not root.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy thư mục dữ liệu")
    return root, False


def _lock(user: TokenPayload, limited: bool) -> store.user_lock:
    return store.user_lock(user.user_id if limited else 0)  # the data area is one for everybody: one lock


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


def _resolve(root: Path, raw: str, limited: bool = True) -> Resolved:
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


def _directory(root: Path, raw: str, limited: bool = True) -> Resolved:
    target = _resolve(root, raw, limited)
    if not target.real.is_dir():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Đường dẫn không phải thư mục")
    return target


def check_new_entry(root: Path, parent: Resolved, name: str, limited: bool = True) -> Path:
    """The real path a new child `name` of `parent` would get, after depth / collision / count limits."""
    if len(parent.parts) + 1 > MAX_DEPTH:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Đường dẫn quá sâu (tối đa 6 cấp)")
    target = parent.real / name
    if os.path.lexists(target):
        raise HTTPException(status.HTTP_409_CONFLICT, "Tên này đã tồn tại")
    if not limited:
        return target
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


@router.get("/entries")
def list_files(path: VirtualPath = "/", area: Area = "mine", user: TokenPayload = Depends(get_current_user)) -> dict:
    root, limited = _area(user, area)
    target = _directory(root, path, limited)
    with os.scandir(target.real) as scan:
        entries = [item for item in map(_entry, scan) if item is not None]
    entries.sort(key=lambda e: (e["type"] != "folder", e["name"].casefold(), e["name"]))
    if not limited:  # no quota in the data area: its size is not counted (the tree is large), and a quota of 0 means "none"
        return {"path": target.virtual, "entries": entries[:DATA_MAX_LIST_ENTRIES], "total": len(entries), "usage": {"usedBytes": 0, "quotaBytes": 0}}
    return {
        "path": target.virtual,
        "entries": entries[:MAX_LIST_ENTRIES],
        "total": len(entries),
        "usage": {"usedBytes": _scan(root)[0], "quotaBytes": QUOTA_BYTES},
    }


@router.post("/folder", status_code=status.HTTP_201_CREATED)
def create_folder(body: FolderIn, area: Area = "mine", user: TokenPayload = Depends(writer)) -> dict:
    name = _name(body.name)
    root, limited = _area(user, area)
    with _lock(user, limited):
        parent = _directory(root, body.path, limited)
        os.mkdir(check_new_entry(root, parent, name, limited))
    return {"name": name}


def spool(source, limit: int) -> tuple[Path, int]:
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


@router.post("/upload", status_code=status.HTTP_201_CREATED)
def upload(
    file: Annotated[UploadFile, File()],
    path: VirtualPath = "/",
    area: Area = "mine",
    replace: bool = False,
    user: TokenPayload = Depends(writer),
) -> dict:
    """Put a file in a folder. A name that is taken is refused, unless `replace` is asked for in the person's own area: then what the file was is kept as a version."""
    name = _name(re.split(r"[\\/]", file.filename or "")[-1])  # a client may send a path: keep the last part
    root, limited = _area(user, area)
    with _lock(user, limited):
        parent = _directory(root, path, limited)
        existing = parent.real / name
        replacing = replace and limited and existing.is_file() and not existing.is_symlink()
        target = existing if replacing else check_new_entry(root, parent, name, limited)
        used = _scan(root)[0] if limited else 0
        temp, size = spool(file.file, MAX_FILE_BYTES)
        try:
            if limited and used - (existing.stat().st_size if replacing else 0) + size > QUOTA_BYTES:
                raise HTTPException(413, "Vượt quá dung lượng 100 MB")
            if replacing:
                versions.keep(user.user_id, _join(parent.virtual, name), existing)
            os.replace(temp, target)  # atomic; without `replace` the collision check and the user lock rule out an overwrite
        finally:
            temp.unlink(missing_ok=True)
    return {"name": name, "size": size, **({"replaced": True} if replacing else {})}


def _join(folder: str, name: str) -> str:
    return f"/{name}" if folder == "/" else f"{folder}/{name}"


@router.get("/versions")
def list_versions(path: VirtualPath, user: TokenPayload = Depends(get_current_user)) -> dict:
    """The versions kept of the file at `path` (what it was before it was replaced), the newest first."""
    return {"versions": [{"id": meta["id"], "size": meta["size"], "savedAt": meta["savedAt"]} for meta in versions.of_path(user.user_id, path)], "keepDays": versions.KEEP_DAYS}


class VersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(max_length=64)


@router.post("/versions/restore")
def restore_version(body: VersionIn, user: TokenPayload = Depends(writer)) -> dict:
    """Put a version back as the file; what the file is now is kept as a version, so this can be undone."""
    root, _ = _area(user, "mine")
    with _lock(user, True):
        found = versions.find(user.user_id, body.id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phiên bản")
        folder, meta = found
        try:
            parent = _directory(root, meta["path"].rsplit("/", 1)[0] or "/")
        except HTTPException:
            raise HTTPException(status.HTTP_409_CONFLICT, "Thư mục của tệp không còn") from None
        target = parent.real / meta["name"]
        if target.exists() and not target.is_file():
            raise HTTPException(status.HTTP_409_CONFLICT, "Tên này đã tồn tại")
        current = target.stat().st_size if target.is_file() else 0
        if _scan(root)[0] - current + meta["size"] > QUOTA_BYTES:
            raise HTTPException(413, "Vượt quá dung lượng 100 MB")
        if target.is_file():
            versions.keep(user.user_id, meta["path"], target)
        temp = target.with_name(f".restore-{secrets.token_hex(6)}")
        shutil.copy2(folder / versions.ITEM, temp)
        os.replace(temp, target)
        versions.drop(user.user_id, body.id)
    return {"name": meta["name"], "path": parent.virtual}


@router.delete("/versions", status_code=status.HTTP_204_NO_CONTENT)
def drop_version(id: Annotated[str, Query(max_length=64)], user: TokenPayload = Depends(writer)) -> Response:
    with _lock(user, True):
        if not versions.drop(user.user_id, id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phiên bản")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/download")
def download(path: VirtualPath, area: Area = "mine", user: TokenPayload = Depends(get_current_user)) -> FileResponse:
    root, limited = _area(user, area)
    target = _resolve(root, path, limited)
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


@router.delete("/entries", status_code=status.HTTP_204_NO_CONTENT)
def delete(path: VirtualPath, area: Area = "mine", user: TokenPayload = Depends(writer)) -> Response:
    root, limited = _area(user, area)
    with _lock(user, limited):
        target = _resolve(root, path, limited)
        if not target.parts:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể xóa thư mục gốc")
        if not limited and len(target.parts) == 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể xóa thư mục ở cấp cao nhất của dữ liệu máy chủ")
        if target.real.is_dir():
            if _scan(target.real)[1] > (MAX_DELETE_ENTRIES if limited else DATA_MAX_DELETE_ENTRIES):
                raise HTTPException(status.HTTP_409_CONFLICT, "Thư mục có quá nhiều mục để xóa cùng lúc")
            (trash.put(user.user_id, target.real, target.parts) if limited else shutil.rmtree(target.real))
        else:
            (trash.put(user.user_id, target.real, target.parts) if limited else target.real.unlink())  # a person's delete goes to the trash; the data area has none
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class RestoreIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(max_length=64)


@router.get("/trash")
def list_trash(user: TokenPayload = Depends(get_current_user)) -> dict:
    """What the person deleted and can still put back (the newest first); it is erased for good after a while."""
    return {"entries": trash.entries(user.user_id), "keepDays": trash.KEEP_DAYS}


def free_name(parent: Path, name: str) -> str:
    """`name` when nothing of that name is in `parent`, else `name (2)`, `name (3)`..., short enough to be a name."""
    if not os.path.lexists(parent / name):
        return name
    stem, dot, extension = name.rpartition(".") if "." in name[1:] else (name, "", "")
    for number in range(2, 1000):
        candidate = f"{stem} ({number}){dot}{extension}"
        if len(candidate) <= MAX_NAME_LENGTH and not os.path.lexists(parent / candidate):
            return candidate
    raise HTTPException(status.HTTP_409_CONFLICT, "Tên này đã tồn tại")


@router.post("/trash/restore")
def restore(body: RestoreIn, user: TokenPayload = Depends(writer)) -> dict:
    """Put an item back where it was (at the top when that folder is gone; under a new name when the name is taken)."""
    root, _ = _area(user, "mine")
    with _lock(user, True):
        found = trash.find(user.user_id, body.id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy trong thùng rác")
        folder, meta = found
        try:
            parent = _directory(root, meta["parent"])
        except HTTPException:
            parent = _directory(root, "/")  # the folder it was in is gone
        name = free_name(parent.real, meta["name"])
        target = check_new_entry(root, parent, name)
        if _scan(root)[0] + meta["size"] > QUOTA_BYTES:
            raise HTTPException(413, "Vượt quá dung lượng 100 MB")
        shutil.move(str(folder / trash.ITEM), str(target))
        shutil.rmtree(folder, ignore_errors=True)
    return {"name": name, "path": parent.virtual}


@router.delete("/trash", status_code=status.HTTP_204_NO_CONTENT)
def erase_trash(id: Annotated[str | None, Query(max_length=64)] = None, user: TokenPayload = Depends(writer)) -> Response:
    """Erase one item of the trash for good (`id`), or all of it."""
    with _lock(user, True):
        if id is not None and trash.find(user.user_id, id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy trong thùng rác")
        trash.erase(user.user_id, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/rename")
def rename(body: RenameIn, area: Area = "mine", user: TokenPayload = Depends(writer)) -> dict:
    new_name = _name(body.new_name)
    root, limited = _area(user, area)
    with _lock(user, limited):
        target = _resolve(root, body.path, limited)
        if not target.parts:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể đổi tên thư mục gốc")
        if not limited and len(target.parts) == 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể đổi tên thư mục ở cấp cao nhất của dữ liệu máy chủ")
        if new_name != target.parts[-1]:
            destination = target.real.parent / new_name
            if os.path.lexists(destination):
                raise HTTPException(status.HTTP_409_CONFLICT, "Tên này đã tồn tại")
            os.rename(target.real, destination)
    return {"name": new_name}


@router.post("/move")
def move(body: MoveIn, area: Area = "mine", user: TokenPayload = Depends(writer)) -> dict:
    """Move a file or folder into another folder of the same area (drag and drop in the explorer)."""
    root, limited = _area(user, area)
    with _lock(user, limited):
        target = _resolve(root, body.path, limited)
        if not target.parts:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể di chuyển thư mục gốc")
        if not limited and len(target.parts) == 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể di chuyển thư mục ở cấp cao nhất của dữ liệu máy chủ")
        destination_folder = _directory(root, body.to_folder, limited)
        if destination_folder.parts[: len(target.parts)] == target.parts:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể đưa thư mục vào chính nó")
        if destination_folder.parts == target.parts[:-1]:
            return {"moved": False}
        new_path = check_new_entry(root, destination_folder, target.parts[-1], limited)
        os.rename(target.real, new_path)
    return {"moved": True}


class CopyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(max_length=700)
    to_folder: str = Field(alias="toFolder", max_length=700)


@router.post("/copy", status_code=status.HTTP_201_CREATED)
def copy(body: CopyIn, area: Area = "mine", user: TokenPayload = Depends(writer)) -> dict:
    """Copy a file or a folder (with all it holds) into another folder of the same area. The copy keeps the name; a name that is taken is refused."""
    root, limited = _area(user, area)
    with _lock(user, limited):
        source = _resolve(root, body.path, limited)
        if not source.parts:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể sao chép thư mục gốc")
        destination_folder = _directory(root, body.to_folder, limited)
        if source.real.is_dir() and destination_folder.parts[: len(source.parts)] == source.parts:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể sao chép thư mục vào chính nó")
        new_path = check_new_entry(root, destination_folder, source.parts[-1], limited)
        if source.real.is_dir():
            shutil.copytree(source.real, new_path, symlinks=True)
        else:
            shutil.copy2(source.real, new_path, follow_symlinks=False)
    return {"copied": True, "name": source.parts[-1]}


MAX_SEARCH_HITS = 200


@router.get("/search-folder")
def search_folder(path: VirtualPath = "/", q: Annotated[str, Query(min_length=1, max_length=120)] = "", area: Area = "mine", user: TokenPayload = Depends(get_current_user)) -> dict:
    """The files and folders whose name holds `q`, in the folder and all the folders below it (at most 200 hits)."""
    root, limited = _area(user, area)
    start = _directory(root, path, limited)
    needle = q.strip().casefold()
    hits: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(start.real):
        here = Path(dirpath)
        relative = here.relative_to(start.real).parts
        for name, is_dir in [(n, True) for n in dirnames] + [(n, False) for n in filenames]:
            if needle not in name.casefold():
                continue
            child = here / name
            try:
                info = child.stat()
            except OSError:
                continue
            hits.append({
                "name": name,
                "path": to_virtual([*start.parts, *relative, name]),
                "type": "folder" if is_dir else "file",
                "size": 0 if is_dir else info.st_size,
                "modifiedAt": int(info.st_mtime),
            })
            if len(hits) >= MAX_SEARCH_HITS:
                return {"entries": hits, "more": True}
    return {"entries": hits, "more": False}
