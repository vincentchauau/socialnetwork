"""Disk storage for photo files. Names are always server-generated."""

import os
import re
import uuid
from pathlib import Path

DEFAULT_UPLOAD_DIR = "./uploads"
STORED_NAME_PATTERN = re.compile(r"^[0-9a-f]{32}(_thumb)?\.(jpg|png|webp|gif)$")


class PhotoStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "PhotoStorage":
        return cls(Path(os.environ.get("UPLOAD_DIR", DEFAULT_UPLOAD_DIR)))

    def _path(self, name: str) -> Path:
        if not STORED_NAME_PATTERN.fullmatch(name):
            raise ValueError("Invalid stored file name")
        path = (self._root / name).resolve()
        if path.parent != self._root:
            raise ValueError("Invalid stored file name")
        return path

    def save(self, data: bytes, thumb_data: bytes, extension: str) -> tuple[str, str]:
        """Write both files; return (image_name, thumb_name)."""
        stem = uuid.uuid4().hex
        image_name, thumb_name = f"{stem}.{extension}", f"{stem}_thumb.webp"
        self._path(image_name).write_bytes(data)
        self._path(thumb_name).write_bytes(thumb_data)
        return image_name, thumb_name

    def resolve(self, name: str) -> Path | None:
        path = self._path(name)
        return path if path.is_file() else None

    def delete(self, *names: str) -> None:
        for name in names:
            self._path(name).unlink(missing_ok=True)
