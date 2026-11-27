"""Serve a video file with HTTP Range support, so the browser can seek in it."""

import logging
import re
from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from fastapi.responses import Response, StreamingResponse

logger = logging.getLogger(__name__)
CHUNK_BYTES = 1024 * 1024
RANGE_PATTERN = re.compile(r"bytes=(\d*)-(\d*)")
MEDIA_TYPES = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}


def parse_range(header: str, size: int) -> tuple[int, int] | None:
    """(start, end), both inclusive, for one 'bytes=a-b' range; None when the header is not a satisfiable range."""
    match = RANGE_PATTERN.fullmatch(header.strip())
    if not match:
        return None
    first, last = match.groups()
    if first == "" and last == "":
        return None
    if first == "":
        start, end = max(size - int(last), 0), size - 1
    else:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    if start > end or start >= size:
        return None
    return start, end


def read_chunks(path: Path, start: int, end: int) -> Iterator[bytes]:
    remaining = end - start + 1
    with path.open("rb") as handle:
        handle.seek(start)
        while remaining > 0:
            chunk = handle.read(min(CHUNK_BYTES, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def video_response(path: Path, request: Request) -> Response:
    """The whole file, or the requested byte range (206) when the browser asks for one."""
    try:
        size = path.stat().st_size
        media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
        header = request.headers.get("range")
        if header is None:
            return StreamingResponse(read_chunks(path, 0, size - 1), media_type=media_type,
                                     headers={"Accept-Ranges": "bytes", "Content-Length": str(size)})
        span = parse_range(header, size)
        if span is None:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        start, end = span
        return StreamingResponse(
            read_chunks(path, start, end), status_code=206, media_type=media_type,
            headers={"Accept-Ranges": "bytes", "Content-Range": f"bytes {start}-{end}/{size}",
                     "Content-Length": str(end - start + 1)},
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("video_response failed")
        raise
