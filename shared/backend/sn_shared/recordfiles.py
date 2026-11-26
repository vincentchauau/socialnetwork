"""Files kept with the rows of a table: `{root}/{database}/{table}/{column}/{row_id}/{file}` (see `records_router`).

A file cell holds the path of its file, relative to `root` (`market/products/image/12/cover.png`). Only the kinds a column
allows are kept, each under a size limit, and the name is cleaned so no path leaves its folder.
"""

import os
import re
from pathlib import Path

ROOT_ENV = "RECORDS_DATA_DIR"
DEFAULT_ROOT = "data/records"

# Largest file each kind takes, in bytes.
LIMITS = {"image": 10 * 1024 * 1024, "audio": 20 * 1024 * 1024, "video": 100 * 1024 * 1024, "file": 20 * 1024 * 1024}
# Extensions each kind accepts (the "file" kind takes any of them).
EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp"},
    "audio": {".mp3", ".wav", ".ogg", ".m4a", ".flac"},
    "video": {".mp4", ".webm", ".mov", ".mkv"},
}
CONTENT_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".flac": "audio/flac",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".mkv": "video/x-matroska",
}
UNSAFE = re.compile(r"[^A-Za-z0-9._ -]+")
PART = re.compile(r"^[A-Za-z0-9_.~-]+$")


class FileRefused(ValueError):
    """A file that the column, kind or size does not allow."""


def root() -> Path:
    return Path(os.environ.get(ROOT_ENV, DEFAULT_ROOT)).resolve()


def clean_name(name: str) -> str:
    """The file's own name with nothing that could leave its folder: no path, no odd characters."""
    base = os.path.basename(name.replace("\\", "/")).strip()
    cleaned = UNSAFE.sub("_", base).strip("._ ")
    if not cleaned:
        raise FileRefused("the file needs a name")
    return cleaned[:120]


def check(kind: str, name: str, size: int) -> str:
    """The name to keep for a file of `kind`, or FileRefused when its extension or size is not allowed."""
    cleaned = clean_name(name)
    extension = os.path.splitext(cleaned)[1].lower()
    allowed = EXTENSIONS.get(kind)
    if allowed is not None and extension not in allowed:
        raise FileRefused(f"a {kind} must be one of: {', '.join(sorted(allowed))}")
    if size > LIMITS.get(kind, LIMITS["file"]):
        raise FileRefused(f"a {kind} can be at most {LIMITS.get(kind, LIMITS['file']) // (1024 * 1024)} MB")
    return cleaned


def relative_path(database: str, table: str, column: str, row_id: str, name: str) -> str:
    parts = (database, table, column, row_id, name)
    if not all(PART.match(part) for part in parts):
        raise FileRefused("a path part has characters that are not allowed")
    return "/".join(parts)


def location(relative: str) -> Path:
    """The file a stored path names, always inside `root`."""
    target = (root() / relative).resolve()
    if root() not in target.parents:
        raise FileRefused("the path leaves the records folder")
    return target


def content_type(name: str) -> str:
    return CONTENT_TYPES.get(os.path.splitext(name)[1].lower(), "application/octet-stream")


def save(relative: str, data: bytes) -> None:
    target = location(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


EXCEL_LIMIT = 5 * 1024 * 1024
EXCEL_EXTENSIONS = {".xlsx"}


def read_excel(data: bytes, max_rows: int) -> list[dict]:
    """The rows of the first sheet of an .xlsx: the first line names the columns, each next line is one row.

    Empty lines are skipped; a date becomes its ISO text. Refused when the file is too big, not a workbook, or has more rows than
    `max_rows`.
    """
    import io
    from datetime import date, datetime

    from openpyxl import load_workbook

    if len(data) > EXCEL_LIMIT:
        raise FileRefused(f"an Excel file can be at most {EXCEL_LIMIT // (1024 * 1024)} MB")
    try:
        sheet = load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
    except (OSError, ValueError, KeyError, IndexError) as exc:
        raise FileRefused("this is not an Excel (.xlsx) file") from exc
    lines = sheet.iter_rows(values_only=True)
    header = next(lines, None)
    if not header:
        return []
    names = [str(name).strip() if name is not None else "" for name in header]
    rows: list[dict] = []
    for line in lines:
        values = {}
        for name, value in zip(names, line):
            if not name or value is None or (isinstance(value, str) and value.strip() == ""):
                continue
            values[name] = value.isoformat() if isinstance(value, (datetime, date)) else value
        if values:
            rows.append(values)
        if len(rows) > max_rows:
            raise FileRefused(f"at most {max_rows} rows per file")
    return rows


MEDIA_KINDS = {".jpg": "image", ".jpeg": "image", ".png": "image", ".gif": "image", ".webp": "image",
               ".mp3": "audio", ".wav": "audio", ".ogg": "audio", ".m4a": "audio", ".flac": "audio",
               ".mp4": "video", ".webm": "video", ".mov": "video", ".mkv": "video"}


def folder_of(database: str, table: str, column: str, row_id: str) -> str:
    """The folder of one cell of one row: every file of that cell lives in it (`market/showcases/cover/3`)."""
    parts = (database, table, column, row_id)
    if not all(PART.match(part) for part in parts):
        raise FileRefused("a path part has characters that are not allowed")
    return "/".join(parts)


def files_of(value: str) -> list[str]:
    """The files a cell holds: the files of its folder, or the one file the cell names (a cell made before folders)."""
    if not value:
        return []
    if os.path.splitext(value)[1].lower() in MEDIA_KINDS or os.path.splitext(value)[1].lower() in CONTENT_TYPES:
        return [value]
    folder = location(value)
    if not folder.is_dir():
        return []
    return sorted(f"{value}/{entry.name}" for entry in folder.iterdir() if entry.is_file())


def kind_of_file(name: str) -> str:
    return MEDIA_KINDS.get(os.path.splitext(name)[1].lower(), "file")


def remove(relative: str) -> None:
    location(relative).unlink(missing_ok=True)
