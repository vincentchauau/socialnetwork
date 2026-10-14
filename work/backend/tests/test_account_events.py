from app import account_events
from app.store import db_path, files_root
from tests.conftest import auth_cookie


def populate(client, user_id, name):
    headers = auth_cookie(user_id, name)
    client.post("/files/folder", json={"path": "/", "name": "d"}, headers=headers)
    client.post("/files/upload", params={"path": "/d"}, files={"file": ("a.txt", b"x", "text/plain")}, headers=headers)
    client.post("/db/query", json={"sql": "CREATE TABLE t (a)"}, headers=headers)


def test_user_deleted_removes_only_that_users_data(client):
    populate(client, 1, "alice")
    populate(client, 2, "bob")
    account_events.on_user_deleted(None, 1)
    assert not files_root(1).exists() and not db_path(1).exists()
    assert (files_root(2) / "d" / "a.txt").exists() and db_path(2).exists()
    assert client.get("/files", headers=auth_cookie(1, "alice")).json()["entries"] == []


def test_user_deleted_is_idempotent_and_ignores_bad_ids(client):
    populate(client, 1, "alice")
    populate(client, 2, "bob")
    for user_id in (1, 1, 99, 0, -1):
        account_events.on_user_deleted(None, user_id)
    assert not files_root(1).exists()
    assert files_root(2).exists()
    assert files_root(0).parent.exists()  # the shared parent directory is untouched


def test_user_deleted_never_follows_a_root_symlink(tmp_path):
    outside = tmp_path / "keep"
    outside.mkdir()
    (outside / "f").write_text("x")
    root = files_root(7)
    root.parent.mkdir(parents=True)
    try:
        root.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        return
    account_events.on_user_deleted(None, 7)
    assert (outside / "f").exists() and not root.is_symlink()


def test_user_deleted_removes_journal_files(client):
    populate(client, 3, "cy")
    for suffix in ("-journal", "-wal", "-shm"):
        (db_path(3).parent / f"3.sqlite3{suffix}").write_text("x")
    account_events.on_user_deleted(None, 3)
    assert list(db_path(3).parent.glob("3.sqlite3*")) == []


def test_rename_is_a_no_op(client):
    populate(client, 1, "alice")
    assert account_events.on_user_renamed(None, 1, "alicia") is None
    assert files_root(1).exists()
