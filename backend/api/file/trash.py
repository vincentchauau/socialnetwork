"""The trash of a person's files: deleting moves a file or a folder here, from where it can be put back or erased for good.

    <FILE_DATA_DIR>/trash/<user_id>/<id>/item        what was deleted (a file, or a folder with all it holds)
    <FILE_DATA_DIR>/trash/<user_id>/<id>/meta.json   its name, where it was, what it is, how big it is, when it was deleted

The trash is not part of the person's tree (it does not count for the quota or for the number of entries), so it has limits of its own: what stays
more than `KEEP_DAYS` days goes, and when the trash holds more than `MAX_ITEMS` or `MAX_BYTES` the oldest go first. Only the person's own area has one:
what an admin deletes in the data area is gone at once.
"""

import json
import os
import secrets
import shutil
import time
from pathlib import Path

from api.file import store

KEEP_DAYS = 30
MAX_ITEMS = 100
MAX_BYTES = 200 * 1024 * 1024
ID_BYTES = 8
META = "meta.json"
ITEM = "item"


def trash_dir(user_id: int) -> Path:
    return store.data_dir() / "trash" / str(int(user_id))


def size_of(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for current, _dirs, names in os.walk(path, followlinks=False):
        for name in names:
            try:
                total += os.lstat(os.path.join(current, name)).st_size
            except OSError:
                continue
    return total


def put(user_id: int, real: Path, parts: tuple[str, ...]) -> dict:
    """Move `real` (the file or folder at the virtual path `parts`) into the trash; returns what is recorded about it."""
    home = trash_dir(user_id)
    home.mkdir(parents=True, exist_ok=True)
    entry_id = secrets.token_hex(ID_BYTES)
    folder = home / entry_id
    folder.mkdir()
    meta = {
        "id": entry_id,
        "name": parts[-1],
        "parent": "/" + "/".join(parts[:-1]),
        "type": "folder" if real.is_dir() else "file",
        "size": size_of(real),
        "deletedAt": int(time.time()),
        "seq": time.time_ns(),  # tells apart what was deleted within the same second
    }
    shutil.move(str(real), str(folder / ITEM))
    (folder / META).write_text(json.dumps(meta), encoding="utf-8")
    trim(user_id)
    return meta


def age(meta: dict) -> int:
    return int(meta.get("seq", meta["deletedAt"] * 10**9))


def read_trash(folder: Path) -> dict | None:
    try:
        meta = json.loads((folder / META).read_text(encoding="utf-8"))
        return meta if isinstance(meta, dict) and meta.get("id") == folder.name and (folder / ITEM).exists() else None
    except (OSError, ValueError):
        return None


def entries(user_id: int) -> list[dict]:
    """What is in the trash, the newest first; what has stayed too long is erased first."""
    trim(user_id)
    home = trash_dir(user_id)
    if not home.is_dir():
        return []
    found = [meta for meta in (read_trash(folder) for folder in home.iterdir() if folder.is_dir()) if meta]
    return sorted(found, key=age, reverse=True)


def trim(user_id: int) -> None:
    """Erase what is older than KEEP_DAYS, then the oldest while there are too many items or too many bytes."""
    home = trash_dir(user_id)
    if not home.is_dir():
        return
    now = time.time()
    kept = []
    for folder in home.iterdir():
        if not folder.is_dir():
            continue
        meta = read_trash(folder)
        if meta is None or now - meta["deletedAt"] > KEEP_DAYS * 86400:
            shutil.rmtree(folder, ignore_errors=True)
        else:
            kept.append(meta)
    kept.sort(key=age)  # the oldest first
    total = sum(meta["size"] for meta in kept)
    while kept and (len(kept) > MAX_ITEMS or total > MAX_BYTES):
        oldest = kept.pop(0)
        total -= oldest["size"]
        shutil.rmtree(home / oldest["id"], ignore_errors=True)


def find(user_id: int, entry_id: str) -> tuple[Path, dict] | None:
    """The folder that holds an item of the trash and what is recorded about it; None when there is no such item."""
    if not entry_id or not all(char in "0123456789abcdef" for char in entry_id) or len(entry_id) != ID_BYTES * 2:
        return None
    folder = trash_dir(user_id) / entry_id
    meta = read_trash(folder) if folder.is_dir() else None
    return (folder, meta) if meta else None


def erase(user_id: int, entry_id: str | None = None) -> int:
    """Erase one item for good, or the whole trash when no id is given; returns how many items went."""
    if entry_id is not None:
        found = find(user_id, entry_id)
        if found is None:
            return 0
        shutil.rmtree(found[0], ignore_errors=True)
        return 1
    count = len(entries(user_id))
    shutil.rmtree(trash_dir(user_id), ignore_errors=True)
    return count
