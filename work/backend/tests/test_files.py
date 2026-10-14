import io
import os

import pytest

from app import files
from app.store import files_root, incoming_dir
from tests.conftest import auth_cookie


def put(client, headers, name="a.txt", data=b"hello", path="/", content_type="text/plain"):
    return client.post(
        "/files/upload", params={"path": path}, files={"file": (name, data, content_type)}, headers=headers
    )


def mkdir(client, headers, name, path="/"):
    return client.post("/files/folder", json={"path": path, "name": name}, headers=headers)


def leftovers():
    folder = incoming_dir()
    return list(folder.iterdir()) if folder.exists() else []


def test_requires_login(client):
    for call in (
        lambda: client.get("/files"),
        lambda: client.get("/files/download", params={"path": "/a"}),
        lambda: client.delete("/files", params={"path": "/a"}),
        lambda: client.post("/files/folder", json={"path": "/", "name": "x"}),
    ):
        assert call().status_code == 401


def test_empty_listing(client, alice):
    body = client.get("/files", params={"path": "/"}, headers=alice).json()
    assert body == {"path": "/", "entries": [], "usage": {"usedBytes": 0, "quotaBytes": 100 * 1024 * 1024}}


def test_create_upload_list_sorted_folders_first(client, alice):
    assert mkdir(client, alice, "zeta").status_code == 201
    assert mkdir(client, alice, "Alpha").json() == {"name": "Alpha"}
    r = put(client, alice, "b.txt", b"12345")
    assert r.status_code == 201 and r.json() == {"name": "b.txt", "size": 5}
    put(client, alice, "a.txt", b"1")
    body = client.get("/files", headers=alice).json()
    assert [(e["name"], e["type"]) for e in body["entries"]] == [
        ("Alpha", "folder"),
        ("zeta", "folder"),
        ("a.txt", "file"),
        ("b.txt", "file"),
    ]
    sizes = {e["name"]: e["size"] for e in body["entries"]}
    assert sizes["b.txt"] == 5 and sizes["Alpha"] == 0
    assert body["usage"]["usedBytes"] == 6
    assert isinstance(body["entries"][0]["modifiedAt"], int)


def test_nested_upload_and_listing(client, alice):
    mkdir(client, alice, "docs")
    assert put(client, alice, "n.txt", b"x", path="/docs").status_code == 201
    assert client.get("/files", params={"path": "/docs/"}, headers=alice).json()["entries"][0]["name"] == "n.txt"
    assert client.get("/files", params={"path": "/nope"}, headers=alice).status_code == 404
    assert client.get("/files", params={"path": "/docs/n.txt"}, headers=alice).status_code == 400


def test_collisions_return_409(client, alice):
    mkdir(client, alice, "d")
    assert mkdir(client, alice, "d").status_code == 409
    put(client, alice, "f.txt")
    assert put(client, alice, "f.txt", b"other").status_code == 409
    assert client.get("/files/download", params={"path": "/f.txt"}, headers=alice).content == b"hello"
    assert mkdir(client, alice, "f.txt").status_code == 409
    assert leftovers() == []


def test_download_is_always_an_attachment(client, alice):
    html = b"<script>alert(1)</script>"
    put(client, alice, "evil.html", html, content_type="text/html")
    r = client.get("/files/download", params={"path": "/evil.html"}, headers=alice)
    assert r.status_code == 200 and r.content == html
    assert r.headers["content-disposition"].startswith("attachment")
    assert "evil.html" in r.headers["content-disposition"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-security-policy"] == "sandbox"
    assert r.headers["content-type"] == "application/octet-stream"
    assert "no-store" in r.headers["cache-control"]


def test_download_unicode_name_and_missing(client, alice):
    put(client, alice, "báo cáo.txt", b"x")
    r = client.get("/files/download", params={"path": "/báo cáo.txt"}, headers=alice)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    mkdir(client, alice, "dir")
    assert client.get("/files/download", params={"path": "/dir"}, headers=alice).status_code == 404
    assert client.get("/files/download", params={"path": "/"}, headers=alice).status_code == 404
    assert client.get("/files/download", params={"path": "/missing"}, headers=alice).status_code == 404
    assert client.get("/files/download", headers=alice).status_code == 422


def test_upload_filename_with_a_path_keeps_only_the_last_part(client, alice):
    r = put(client, alice, "..\\..\\evil/ok.txt")
    assert r.status_code == 201 and r.json()["name"] == "ok.txt"
    assert (files_root(1) / "ok.txt").exists()


def test_upload_bad_filenames(client, alice):
    assert put(client, alice, "..").status_code == 400
    assert put(client, alice, "con.txt").status_code == 400
    assert put(client, alice, "").status_code in (400, 422)


def test_upload_to_missing_or_file_directory(client, alice):
    assert put(client, alice, path="/nope").status_code == 404
    put(client, alice, "f.txt")
    assert put(client, alice, "g.txt", path="/f.txt").status_code == 400


def test_per_file_cap(client, alice):
    assert put(client, alice, "big.bin", b"0" * files.MAX_FILE_BYTES).status_code == 201
    assert put(client, alice, "bigger.bin", b"0" * (files.MAX_FILE_BYTES + 1)).status_code == 413
    assert leftovers() == []
    assert not (files_root(1) / "bigger.bin").exists()


def test_declared_length_checks(client, alice):
    headers = {**alice, "Content-Type": "multipart/form-data; boundary=x"}
    too_big = client.post(
        "/files/upload", content=b"x", headers={**headers, "Content-Length": str(30 * 1024 * 1024)}
    )
    assert too_big.status_code == 413
    chunked = client.post("/files/upload", content=iter([b"--x--"]), headers=headers)
    assert chunked.status_code == 411


def test_quota(client, alice, monkeypatch):
    monkeypatch.setattr(files, "QUOTA_BYTES", 1000)
    assert put(client, alice, "a.bin", b"0" * 600).status_code == 201
    r = put(client, alice, "b.bin", b"0" * 401)
    assert r.status_code == 413 and "100 MB" in r.json()["detail"]
    assert put(client, alice, "c.bin", b"0" * 400).status_code == 201
    assert not (files_root(1) / "b.bin").exists()
    assert leftovers() == []


def test_quota_is_per_user(client, alice, bob, monkeypatch):
    monkeypatch.setattr(files, "QUOTA_BYTES", 100)
    assert put(client, alice, "a.bin", b"0" * 100).status_code == 201
    assert put(client, bob, "a.bin", b"0" * 100).status_code == 201
    assert put(client, alice, "b.bin", b"0").status_code == 413


def test_entry_and_node_limits(client, alice, monkeypatch):
    monkeypatch.setattr(files, "MAX_LIST_ENTRIES", 2)
    assert put(client, alice, "1").status_code == 201
    assert put(client, alice, "2").status_code == 201
    assert put(client, alice, "3").status_code == 409
    assert mkdir(client, alice, "4").status_code == 409
    monkeypatch.setattr(files, "MAX_LIST_ENTRIES", 500)
    monkeypatch.setattr(files, "MAX_NODES_PER_USER", 2)
    assert put(client, alice, "5").status_code == 409
    monkeypatch.setattr(files, "MAX_LIST_ENTRIES", 1)
    assert len(client.get("/files", headers=alice).json()["entries"]) == 1  # the listing is capped


def test_depth_limit(client, alice):
    path = "/"
    for level in range(6):
        assert mkdir(client, alice, f"d{level}", path=path).status_code == 201
        path = path.rstrip("/") + f"/d{level}"
    assert mkdir(client, alice, "deeper", path=path).status_code == 400
    assert put(client, alice, "f.txt", path=path).status_code == 400
    assert client.get("/files", params={"path": "/a/b/c/d/e/f/g"}, headers=alice).status_code == 400


def test_delete_file_and_folder_recursively(client, alice):
    mkdir(client, alice, "d")
    mkdir(client, alice, "sub", path="/d")
    put(client, alice, "x.txt", path="/d/sub")
    put(client, alice, "y.txt")
    assert client.delete("/files", params={"path": "/y.txt"}, headers=alice).status_code == 204
    assert client.delete("/files", params={"path": "/d"}, headers=alice).status_code == 204
    assert client.get("/files", headers=alice).json()["entries"] == []
    assert client.delete("/files", params={"path": "/d"}, headers=alice).status_code == 404
    assert client.delete("/files", params={"path": "/"}, headers=alice).status_code == 400


def test_delete_cap(client, alice, monkeypatch):
    mkdir(client, alice, "d")
    put(client, alice, "1", path="/d")
    put(client, alice, "2", path="/d")
    monkeypatch.setattr(files, "MAX_DELETE_ENTRIES", 1)
    assert client.delete("/files", params={"path": "/d"}, headers=alice).status_code == 409
    assert (files_root(1) / "d" / "1").exists()


def test_rename(client, alice):
    put(client, alice, "a.txt")
    put(client, alice, "b.txt")

    def rename(path, new_name):
        return client.post("/files/rename", json={"path": path, "newName": new_name}, headers=alice)

    r = rename("/a.txt", "c.txt")
    assert r.status_code == 200 and r.json() == {"name": "c.txt"}
    assert rename("/c.txt", "b.txt").status_code == 409
    assert rename("/c.txt", "c.txt").status_code == 200
    assert rename("/c.txt", "../x").status_code == 400
    assert rename("/c.txt", "a/b").status_code == 400
    assert rename("/zzz", "q").status_code == 404
    assert rename("/", "q").status_code == 400
    assert client.post("/files/rename", json={"path": "/c.txt"}, headers=alice).status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/../x", "/..", "../../etc/passwd", "etc/passwd", "/a/../../x", "..\\x", "/..\\x", "/a\\b", "/a\x00b",
        "/%2e%2e/x", "/\u202e/x", "/.", "/./x", "C:\\Windows\\win.ini", "/C:/Windows", "//server/share", "/a//b",
        "/" + "a/" * 20, "/" + "x" * 500, "/con", "/trail.", "",
    ],
)
def test_path_traversal_attempts_never_succeed(client, alice, path):
    put(client, alice, "safe.txt")
    calls = (
        lambda: client.get("/files", params={"path": path}, headers=alice),
        lambda: client.get("/files/download", params={"path": path}, headers=alice),
        lambda: client.delete("/files", params={"path": path}, headers=alice),
        lambda: client.post("/files/rename", json={"path": path, "newName": "z"}, headers=alice),
        lambda: client.post("/files/folder", json={"path": path, "name": "z"}, headers=alice),
        lambda: put(client, alice, "z", path=path),
    )
    for call in calls:
        assert call().status_code in (400, 404, 422)
    assert (files_root(1) / "safe.txt").exists()


def test_literal_percent_names_stay_inside(client, alice):
    assert mkdir(client, alice, "%2e%2e").status_code == 201
    assert put(client, alice, "x", path="/%2e%2e").status_code == 201
    assert (files_root(1) / "%2e%2e" / "x").exists()


def test_url_path_segments_never_reach_the_filesystem(client, alice):
    put(client, alice, "a.txt")
    for url in ("/a.txt", "/files/a.txt", "/../etc/passwd", "/files/../a.txt", "/%2e%2e/%2e%2e/etc/passwd"):
        assert client.get(url, headers=alice).status_code in (404, 405)


def test_symlink_in_the_sandbox_is_not_followed(client, alice, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    root = files_root(1)
    root.mkdir(parents=True)
    try:
        (root / "dirlink").symlink_to(outside, target_is_directory=True)
        (root / "filelink").symlink_to(outside / "secret.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    assert client.get("/files", headers=alice).json()["entries"] == []  # links are not listed
    for path in ("/dirlink", "/dirlink/secret.txt", "/filelink"):
        assert client.get("/files/download", params={"path": path}, headers=alice).status_code == 400
        assert client.get("/files", params={"path": path}, headers=alice).status_code == 400
        assert client.delete("/files", params={"path": path}, headers=alice).status_code == 400
    assert put(client, alice, "x", path="/dirlink").status_code == 400
    assert (outside / "secret.txt").read_text() == "secret"
    assert not (outside / "x").exists()


def test_users_are_isolated(client, alice, bob):
    mkdir(client, alice, "private")
    put(client, alice, "secret.txt", b"alice only", path="/private")
    assert client.get("/files", params={"path": "/private"}, headers=bob).status_code == 404
    assert client.get("/files/download", params={"path": "/private/secret.txt"}, headers=bob).status_code == 404
    assert client.delete("/files", params={"path": "/private"}, headers=bob).status_code == 404
    assert client.post("/files/rename", json={"path": "/private", "newName": "mine"}, headers=bob).status_code == 404
    for sneaky in ("/../1/private/secret.txt", "/../../files/1/private"):
        assert client.get("/files/download", params={"path": sneaky}, headers=bob).status_code == 400
    assert client.get("/files", headers=bob).json()["entries"] == []
    assert (files_root(1) / "private" / "secret.txt").read_bytes() == b"alice only"


def test_origin_check_on_unsafe_routes(client, alice):
    evil = {**alice, "Origin": "https://evil.example"}
    assert client.post("/files/folder", json={"path": "/", "name": "x"}, headers=evil).status_code == 403
    assert client.delete("/files", params={"path": "/x"}, headers=evil).status_code == 403
    assert client.get("/files", headers=evil).status_code == 200  # safe method
    good = {**alice, "Origin": "http://localhost:8080"}
    assert client.post("/files/folder", json={"path": "/", "name": "x"}, headers=good).status_code == 201


def test_write_rate_limit(client, alice):
    codes = [mkdir(client, alice, f"f{i}").status_code for i in range(61)]
    assert codes[:60] == [201] * 60 and codes[60] == 429
    assert mkdir(client, auth_cookie(5, "eve"), "x").status_code == 201


def test_unknown_body_fields_are_rejected(client, alice):
    r = client.post("/files/folder", json={"path": "/", "name": "x", "extra": 1}, headers=alice)
    assert r.status_code == 422


def test_scan_ignores_unreadable_entries(tmp_path, monkeypatch):
    root = tmp_path / "r"
    root.mkdir()
    (root / "a").write_bytes(b"123")
    real = os.lstat

    def flaky(path, *args, **kwargs):
        if str(path).endswith("a"):
            raise OSError("boom")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(files.os, "lstat", flaky)
    assert files._scan(root) == (0, 1)


def test_spool_from_stream(tmp_path, monkeypatch):
    monkeypatch.setenv("WORK_DATA_DIR", str(tmp_path))
    path, size = files._spool(io.BytesIO(b"abc"), 10)
    assert size == 3 and path.read_bytes() == b"abc"
