"""The data area of the file manager: the data directory of the backend, for an admin only."""

import pytest

from tests.file.conftest import auth_cookie

ADMIN = auth_cookie(9, "root", group="admin")


@pytest.fixture
def data(tmp_path, monkeypatch):
    root = tmp_path / "data"
    (root / "Galleries" / "sub").mkdir(parents=True)
    (root / "Galleries" / "a.jpg").write_bytes(b"jpg")
    (root / "notes").mkdir()
    for app_folder in ("photos", "work"):  # the folders of the apps are there too
        (root / app_folder).mkdir()
    (root / "photos" / "p.jpg").write_bytes(b"app")
    monkeypatch.setenv("DATA_ROOT", str(root))
    return root


def test_only_an_admin_goes_into_the_data_area(client, alice, data):
    for call in (lambda h: client.get("/entries", params={"area": "data"}, headers=h), lambda h: client.get("/download", params={"area": "data", "path": "/Galleries/a.jpg"}, headers=h)):
        assert call(alice).status_code == 403
        assert call({}).status_code == 401
    assert client.post("/folder", params={"area": "data"}, json={"path": "/", "name": "x"}, headers=alice).status_code == 403
    assert client.get("/entries", params={"area": "nowhere"}, headers=ADMIN).status_code == 422


def test_an_admin_lists_reads_and_makes_things_in_the_whole_data_directory(client, data):
    listing = client.get("/entries", params={"area": "data"}, headers=ADMIN).json()
    assert [e["name"] for e in listing["entries"]] == ["Galleries", "notes", "photos", "work"] and listing["usage"]["quotaBytes"] == 0
    assert [e["name"] for e in client.get("/entries", params={"area": "data", "path": "/Galleries"}, headers=ADMIN).json()["entries"]] == ["sub", "a.jpg"]
    assert client.get("/download", params={"area": "data", "path": "/Galleries/a.jpg"}, headers=ADMIN).content == b"jpg"
    assert client.post("/folder", params={"area": "data"}, json={"path": "/Galleries", "name": "new"}, headers=ADMIN).status_code == 201
    up = client.post("/upload", params={"area": "data", "path": "/Galleries/new"}, files={"file": ("b.txt", b"hello")}, headers=ADMIN)
    assert up.status_code == 201 and (data / "Galleries" / "new" / "b.txt").read_bytes() == b"hello"
    assert client.post("/rename", params={"area": "data"}, json={"path": "/Galleries/new/b.txt", "newName": "c.txt"}, headers=ADMIN).status_code == 200
    assert client.delete("/entries", params={"area": "data", "path": "/Galleries/new"}, headers=ADMIN).status_code == 204
    assert not (data / "Galleries" / "new").exists()


def test_the_folders_at_the_top_of_the_data_are_never_removed_or_renamed(client, data):
    assert client.delete("/entries", params={"area": "data", "path": "/Galleries"}, headers=ADMIN).status_code == 400
    assert client.post("/rename", params={"area": "data"}, json={"path": "/notes", "newName": "other"}, headers=ADMIN).status_code == 400
    assert (data / "Galleries").is_dir() and (data / "notes").is_dir()


def test_every_folder_of_the_data_is_shown_the_folders_of_the_apps_too(client, data):
    names = [e["name"] for e in client.get("/entries", params={"area": "data"}, headers=ADMIN).json()["entries"]]
    assert names == ["Galleries", "notes", "photos", "work"]
    assert [e["name"] for e in client.get("/entries", params={"area": "data", "path": "/photos"}, headers=ADMIN).json()["entries"]] == ["p.jpg"]


def test_it_cannot_leave_the_data_directory(client, data, tmp_path):
    (tmp_path / "secret.txt").write_text("no")
    for path in ("/../secret.txt", "/photos/../../secret.txt", "/photos/..%2f..%2fsecret.txt"):
        assert client.get("/download", params={"area": "data", "path": path}, headers=ADMIN).status_code in (400, 404)


def test_the_area_of_a_person_is_not_the_data_area(client, alice, data):
    client.post("/folder", json={"path": "/", "name": "mine"}, headers=alice)
    assert [e["name"] for e in client.get("/entries", headers=alice).json()["entries"]] == ["mine"]
    assert "mine" not in [e["name"] for e in client.get("/entries", params={"area": "data"}, headers=ADMIN).json()["entries"]]
