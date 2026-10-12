import re

_RANGE_PATTERN = re.compile(r"^bytes=(\d{0,18})-(\d{0,18})$")


class RangeNotSatisfiableError(Exception):
    """The requested byte range lies outside the file (HTTP 416)."""


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Inclusive (start, end) for a single satisfiable range.

    Returns None when the header is absent or not a single well-formed range
    (RFC 9110 says to ignore it and serve the whole file); raises
    RangeNotSatisfiableError when the range is valid but outside the file.
    """
    if header is None:
        return None
    match = _RANGE_PATTERN.match(header.strip())
    if match is None:
        return None
    first, last = match.groups()
    if not first and not last:
        return None
    if not first:  # suffix range: the final N bytes
        suffix = int(last)
        if suffix == 0:
            raise RangeNotSatisfiableError
        return max(size - suffix, 0), size - 1
    start = int(first)
    if start >= size:
        raise RangeNotSatisfiableError
    if not last:
        return start, size - 1
    end = int(last)
    if end < start:
        return None
    return start, min(end, size - 1)
