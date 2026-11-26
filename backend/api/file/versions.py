"""The earlier versions of a file: replacing a file keeps what it was, so that it can be put back.

    <FILE_DATA_DIR>/versions/<user_id>/<id>/item        what the file was
    <FILE_DATA_DIR>/versions/<user_id>/<id>/meta.json   its path, name, size and when it was kept

Like the trash, the versions are outside the person's tree (not in the quota) and have limits of their own: `PER_FILE` for one path (the oldest of the
file goes first), `MAX_BYTES` for the person (the oldest of all go first), and `KEEP_DAYS` days.
"""

import json
import secrets
import shutil
import time
from pathlib import Path

from api.file import store

PER_FILE = 5
MAX_BYTES = 200 * 1024 * 1024
KEEP_DAYS = 90
ID_BYTES = 8
META = "meta.json"
ITEM = "item"


def versions_dir(user_id: int) -> Path:
    return store.data_dir() / "versions" / str(int(user_id))


def age(meta: dict) -> int:
    return int(meta.get("seq", 0))


def read_versions(folder: Path) -> dict | None:
    try:
        meta = json.loads((folder / META).read_text(encoding="utf-8"))
        return meta if isinstance(meta, dict) and meta.get("id") == folder.name and (folder / ITEM).is_file() else None
    except (OSError, ValueError):
        return None


def all_versions(user_id: int) -> list[dict]:
    home = versions_dir(user_id)
    if not home.is_dir():
        return []
    return sorted((meta for meta in (read_versions(folder) for folder in home.iterdir() if folder.is_dir()) if meta), key=age)  # the oldest first


def keep(user_id: int, virtual_path: str, real_file: Path) -> dict:
    """Keep a copy of `real_file` (the file at `virtual_path`) as a version of it."""
    home = versions_dir(user_id)
    home.mkdir(parents=True, exist_ok=True)
    entry_id = secrets.token_hex(ID_BYTES)
    folder = home / entry_id
    folder.mkdir()
    meta = {
        "id": entry_id,
        "path": virtual_path,
        "name": virtual_path.rsplit("/", 1)[-1],
        "size": real_file.stat().st_size,
        "savedAt": int(time.time()),
        "seq": time.time_ns(),  # tells apart what was kept within the same second
    }
    shutil.copy2(real_file, folder / ITEM)
    (folder / META).write_text(json.dumps(meta), encoding="utf-8")
    trim(user_id)
    return meta


def trim(user_id: int) -> None:
    """Erase what is older than KEEP_DAYS, the oldest versions of a file beyond PER_FILE, and then the oldest of all while there are too many bytes."""
    home = versions_dir(user_id)
    now = time.time()
    kept = []
    for meta in all_versions(user_id):
        if now - meta["savedAt"] > KEEP_DAYS * 86400:
            shutil.rmtree(home / meta["id"], ignore_errors=True)
        else:
            kept.append(meta)
    by_path: dict[str, list[dict]] = {}
    for meta in kept:
        by_path.setdefault(meta["path"], []).append(meta)
    for same in by_path.values():
        for old in same[:-PER_FILE]:
            shutil.rmtree(home / old["id"], ignore_errors=True)
            kept.remove(old)
    total = sum(meta["size"] for meta in kept)
    while kept and total > MAX_BYTES:
        oldest = kept.pop(0)
        total -= oldest["size"]
        shutil.rmtree(home / oldest["id"], ignore_errors=True)


def of_path(user_id: int, virtual_path: str) -> list[dict]:
    """The versions kept of the file at `virtual_path`, the newest first."""
    trim(user_id)
    return sorted((meta for meta in all_versions(user_id) if meta["path"] == virtual_path), key=age, reverse=True)


def find(user_id: int, entry_id: str) -> tuple[Path, dict] | None:
    if len(entry_id) != ID_BYTES * 2 or not all(char in "0123456789abcdef" for char in entry_id):
        return None
    folder = versions_dir(user_id) / entry_id
    meta = read_versions(folder) if folder.is_dir() else None
    return (folder, meta) if meta else None


def drop(user_id: int, entry_id: str) -> bool:
    found = find(user_id, entry_id)
    if found is None:
        return False
    shutil.rmtree(found[0], ignore_errors=True)
    return True


def erase_user(user_id: int) -> None:
    shutil.rmtree(versions_dir(user_id), ignore_errors=True)
