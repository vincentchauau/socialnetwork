"""Where the files of the people are (FILE_DATA_DIR) and what is done with them.

    <FILE_DATA_DIR>/<user_id>/...       the file sandbox of a person
    <FILE_DATA_DIR>/incoming/           upload temp files (same filesystem: atomic rename)
"""

import os
import shutil
from pathlib import Path

from sn_shared.userlock import Busy, user_lock  # noqa: F401  (the routes take them from here)

import logging
logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = "/data/file"


def data_dir() -> Path:
    try:
        return Path(os.environ.get("FILE_DATA_DIR", DEFAULT_DATA_DIR))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("data_dir failed")
        raise


def files_root(user_id: int) -> Path:
    try:
        return data_dir() / str(int(user_id))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("files_root failed")
        raise


def incoming_dir() -> Path:
    try:
        return data_dir() / "incoming"
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("incoming_dir failed")
        raise


def erase_user(user_id: int) -> None:
    """Remove the user's file tree; idempotent, never follows symlinks."""
    try:
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
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("erase_user failed")
        raise
