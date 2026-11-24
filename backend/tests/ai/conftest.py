import os
import tempfile

import pytest

# create_app() runs at import time and needs these.
from sn_shared.testing import install_test_keys  # noqa: E402

install_test_keys()
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="art-import-"))

from sn_shared import COOKIE_NAME, create_token


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    install_test_keys(monkeypatch)
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))


def auth_cookie(user_id: int = 1, username: str = "alice") -> dict[str, str]:
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, username)}"}


ALICE = auth_cookie(1, "alice")
BOB = auth_cookie(2, "bob")
ADMIN = {"Cookie": f"{COOKIE_NAME}={create_token(9, 'root', group='admin')}"}
