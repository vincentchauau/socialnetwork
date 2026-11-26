"""Virtual paths of the file sandbox: validation and safe resolution inside one user's root.

A virtual path looks like `/docs/report.txt`. It only ever comes from a query string or a JSON body, never from
a URL path segment. Nothing here follows or creates symbolic links.
"""

import os
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import logging
logger = logging.getLogger(__name__)

MAX_NAME_LENGTH = 100
MAX_DEPTH = 6
MAX_RAW_PATH_LENGTH = 700
FORBIDDEN_NAME_CHARS = frozenset('/\\:*?"<>|\x00')
FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})  # control, format (bidi, zero width), ...
RESERVED_WINDOWS = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
)


class PathError(ValueError):
    """The virtual path or name is not acceptable (HTTP 400)."""


class NotFound(LookupError):
    """Nothing at that virtual path (HTTP 404)."""


def validate_name(raw: str) -> str:
    """One path component: NFC-normalised and checked; returns the normalised name."""
    try:
        if not isinstance(raw, str):
            raise PathError("Tên không hợp lệ")
        name = unicodedata.normalize("NFC", raw)
        if not 1 <= len(name) <= MAX_NAME_LENGTH:
            raise PathError("Tên phải dài từ 1 đến 100 ký tự")
        if name in (".", ".."):
            raise PathError("Tên không hợp lệ")
        if name[-1] in ". ":
            raise PathError("Tên không được kết thúc bằng dấu chấm hoặc dấu cách")
        for char in name:
            if char in FORBIDDEN_NAME_CHARS or unicodedata.category(char) in FORBIDDEN_CATEGORIES:
                raise PathError("Tên chứa ký tự không được phép")
        if name.split(".", 1)[0].rstrip(" ").casefold() in RESERVED_WINDOWS:
            raise PathError("Tên này là tên dành riêng của hệ thống")
        return name
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("validate_name failed")
        raise


def parse_virtual(raw: str) -> list[str]:
    """`/a/b` -> ['a', 'b']; `/` -> []. Must start with '/'; at most one trailing '/'."""
    try:
        if not isinstance(raw, str) or len(raw) > MAX_RAW_PATH_LENGTH or not raw.startswith("/"):
            raise PathError("Đường dẫn không hợp lệ")
        if raw == "/":
            return []
        body = raw[1:]
        if body.endswith("/"):
            body = body[:-1]
        parts = [validate_name(part) for part in body.split("/")]
        if len(parts) > MAX_DEPTH:
            raise PathError("Đường dẫn quá sâu (tối đa 6 cấp)")
        return parts
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("parse_virtual failed")
        raise


def to_virtual(parts: list[str]) -> str:
    try:
        return "/" + "/".join(parts)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("to_virtual failed")
        raise


@dataclass(frozen=True)
class Resolved:
    real: Path
    parts: tuple[str, ...]

    @property
    def virtual(self) -> str:
        try:
            return to_virtual(list(self.parts))
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("virtual failed")
            raise


def resolve(root: Path, raw: str, *, must_exist: bool = True) -> Resolved:
    """The real path of a virtual one, proven to stay inside `root` without crossing a symlink.

    With must_exist=False the last component may be missing (its parent must exist). Raises PathError / NotFound.
    """
    parts = parse_virtual(raw)
    current = root
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            if must_exist or index != len(parts) - 1:
                raise NotFound(raw) from None
            break
        except OSError:
            raise PathError("Đường dẫn không hợp lệ") from None
        if stat.S_ISLNK(info.st_mode):
            raise PathError("Đường dẫn không hợp lệ")
        if index != len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise NotFound(raw)
    real_root = os.path.realpath(root)
    real = os.path.realpath(current)
    try:
        inside = os.path.commonpath([real_root, real]) == real_root
    except ValueError:
        inside = False
    if not inside:
        raise PathError("Đường dẫn không hợp lệ")
    return Resolved(current, tuple(parts))
