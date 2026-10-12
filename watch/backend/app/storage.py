import logging
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024
MP4_BRAND_OFFSET = 4
MP4_BRAND = b"ftyp"
MP4_MAJOR_BRAND_OFFSET = 8
MP4_MAJOR_BRAND_LEN = 4
MP4_MAJOR_BRANDS = frozenset(
    {
        b"isom", b"iso2", b"iso3", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42",
        b"avc1", b"M4V ", b"M4VH", b"M4VP", b"dash", b"mmp4", b"f4v ", b"f4vh", b"MSNV", b"qt  ",
    }
)
WEBM_MAGIC = b"\x1a\x45\xdf\xa3"
HEADER_BYTES = 12
NAME_BYTES = 16
VIDEO_TYPES = {"video/mp4": ".mp4", "video/webm": ".webm"}


class UploadError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class StoredFile:
    name: str
    content_type: str
    size_bytes: int


def sniff_video_type(head: bytes) -> str | None:
    """MP4 or WebM judged by magic bytes only; the client's name and type are ignored."""
    if head[MP4_BRAND_OFFSET : MP4_BRAND_OFFSET + len(MP4_BRAND)] == MP4_BRAND:
        major = head[MP4_MAJOR_BRAND_OFFSET : MP4_MAJOR_BRAND_OFFSET + MP4_MAJOR_BRAND_LEN]
        return "video/mp4" if major in MP4_MAJOR_BRANDS else None
    if head.startswith(WEBM_MAGIC):
        return "video/webm"
    return None


def save_upload(source: BinaryIO, upload_dir: Path, max_bytes: int) -> StoredFile:
    """Stream `source` to a randomly named file; partial files never survive a failure."""
    upload_dir.mkdir(parents=True, exist_ok=True)
    first = source.read(CHUNK_SIZE)
    if not first:
        raise UploadError(422, "The uploaded file is empty")
    content_type = sniff_video_type(first[:HEADER_BYTES])
    if content_type is None:
        raise UploadError(415, "Only MP4 and WebM videos are accepted")

    name = secrets.token_hex(NAME_BYTES) + VIDEO_TYPES[content_type]
    path = upload_dir / name
    total = 0
    try:
        with open(path, "xb") as out:
            chunk = first
            while chunk:
                total += len(chunk)
                if total > max_bytes:
                    raise UploadError(413, "Video is too large")
                out.write(chunk)
                chunk = source.read(CHUNK_SIZE)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return StoredFile(name=name, content_type=content_type, size_bytes=total)


def remove_file(upload_dir: Path, name: str) -> None:
    """Best effort: a file that cannot be removed is logged, never raised."""
    try:
        (upload_dir / name).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete stored video %s", name, exc_info=True)


def stored_bytes(upload_dir: Path, names: Iterable[str]) -> int:
    """Total on-disk size of the named files; missing files count as zero."""
    total = 0
    for name in names:
        try:
            total += (upload_dir / name).stat().st_size
        except OSError:
            continue
    return total


def iter_file(path: Path, start: int, end: int) -> Iterator[bytes]:
    """Yield bytes start..end (inclusive) in chunks."""
    remaining = end - start + 1
    with open(path, "rb") as handle:
        handle.seek(start)
        while remaining > 0:
            chunk = handle.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                return
            remaining -= len(chunk)
            yield chunk
