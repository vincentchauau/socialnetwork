"""Where the files of the people are (FILE_DATA_DIR) and what is done with them.

    <FILE_DATA_DIR>/<user_id>/...       the file sandbox of a person
    <FILE_DATA_DIR>/incoming/           upload temp files (same filesystem: atomic rename)
"""

import os
import shutil
from pathlib import Path

from sn_shared.userlock import Busy, user_lock  # noqa: F401  (the routes take them from here)

DEFAULT_DATA_DIR = "/data/file"


def data_dir() -> Path:
    return Path(os.environ.get("FILE_DATA_DIR", DEFAULT_DATA_DIR))


def files_root(user_id: int) -> Path:
    return data_dir() / str(int(user_id))


def incoming_dir() -> Path:
    return data_dir() / "incoming"


def erase_user(user_id: int) -> None:
    """Remove the user's file tree; idempotent, never follows symlinks."""
    if user_id <= 0:
        return
    with user_lock(user_id):
        root = files_root(user_id)
        if root.is_symlink():
            root.unlink(missing_ok=True)
        elif root.exists():
            shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(data_dir() / "trash" / str(int(user_id)), ignore_errors=True)  # what was deleted goes with the account
        from api.file import shares  # (the links to its files too)

        shares.erase_user(user_id)
        shutil.rmtree(data_dir() / "versions" / str(int(user_id)), ignore_errors=True)  # and its earlier versions
