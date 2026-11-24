"""Deleting a file or a folder puts it in a trash from where it can come back, and the trash has limits of its own."""

import json
import time

from api.file import files, trash
from api.file.store import data_dir, files_root
from tests.file.test_files import mkdir, put


def listing(client, headers):
    return client.get("/trash", headers=headers).json()["entries"]


def test_a_deleted_file_goes_to_the_trash_and_comes_back_where_it_was(client, alice):
    mkdir(client, alice, "docs")
    put(client, alice, "a.txt", data=b"hello", path="/docs")
    assert client.delete("/entries", params={"path": "/docs/a.txt"}, headers=alice).status_code == 204
    assert not (files_root(1) / "docs" / "a.txt").exists()
    [item] = listing(client, alice)
    assert (item["name"], item["parent"], item["type"], item["size"]) == ("a.txt", "/docs", "file", 5)

    restored = client.post("/trash/restore", json={"id": item["id"]}, headers=alice)
    assert restored.status_code == 200 and restored.json() == {"name": "a.txt", "path": "/docs"}
    assert (files_root(1) / "docs" / "a.txt").read_bytes() == b"hello"
    assert listing(client, alice) == []


def test_a_deleted_folder_comes_back_with_all_it_held(client, alice):
    mkdir(client, alice, "d")
    mkdir(client, alice, "sub", path="/d")
    put(client, alice, "x.txt", path="/d/sub")
    client.delete("/entries", params={"path": "/d"}, headers=alice)
    [item] = listing(client, alice)
    assert item["type"] == "folder" and item["size"] == 5
    assert client.post("/trash/restore", json={"id": item["id"]}, headers=alice).status_code == 200
    assert (files_root(1) / "d" / "sub" / "x.txt").exists()


def test_a_name_that_is_taken_gets_a_number_and_a_folder_that_is_gone_means_the_top(client, alice):
    put(client, alice, "a.txt")
    client.delete("/entries", params={"path": "/a.txt"}, headers=alice)
    put(client, alice, "a.txt", data=b"new")
    [item] = listing(client, alice)
    assert client.post("/trash/restore", json={"id": item["id"]}, headers=alice).json()["name"] == "a (2).txt"
    mkdir(client, alice, "gone")
    put(client, alice, "b.txt", path="/gone")
    client.delete("/entries", params={"path": "/gone/b.txt"}, headers=alice)
    client.delete("/entries", params={"path": "/gone"}, headers=alice)
    entry = next(item for item in listing(client, alice) if item["name"] == "b.txt")
    assert client.post("/trash/restore", json={"id": entry["id"]}, headers=alice).json()["path"] == "/"
    assert (files_root(1) / "b.txt").exists()


def test_the_trash_is_each_persons_own(client, alice, bob):
    put(client, alice, "a.txt")
    client.delete("/entries", params={"path": "/a.txt"}, headers=alice)
    [item] = listing(client, alice)
    assert listing(client, bob) == []
    assert client.post("/trash/restore", json={"id": item["id"]}, headers=bob).status_code == 404
    assert client.delete("/trash", params={"id": item["id"]}, headers=bob).status_code == 404
    assert len(listing(client, alice)) == 1


def test_one_item_or_all_of_the_trash_can_be_erased_for_good(client, alice):
    for name in ("1.txt", "2.txt", "3.txt"):
        put(client, alice, name)
        client.delete("/entries", params={"path": f"/{name}"}, headers=alice)
    first = listing(client, alice)[0]
    assert client.delete("/trash", params={"id": first["id"]}, headers=alice).status_code == 204
    assert len(listing(client, alice)) == 2
    assert client.delete("/trash", headers=alice).status_code == 204
    assert listing(client, alice) == []


def test_restoring_respects_the_quota(client, alice, monkeypatch):
    put(client, alice, "big.bin", data=b"x" * 1000)
    client.delete("/entries", params={"path": "/big.bin"}, headers=alice)
    [item] = listing(client, alice)
    put(client, alice, "other.bin", data=b"y" * 500)
    monkeypatch.setattr(files, "QUOTA_BYTES", 1200)
    assert client.post("/trash/restore", json={"id": item["id"]}, headers=alice).status_code == 413
    assert len(listing(client, alice)) == 1  # it is still in the trash


def test_what_has_stayed_too_long_goes_and_too_many_items_push_out_the_oldest(client, alice, monkeypatch):
    for name in ("old.txt", "b.txt", "c.txt"):
        put(client, alice, name)
        client.delete("/entries", params={"path": f"/{name}"}, headers=alice)
    old = next(item for item in listing(client, alice) if item["name"] == "old.txt")
    meta_path = trash.trash_dir(1) / old["id"] / trash.META
    meta = json.loads(meta_path.read_text())
    meta["deletedAt"] = int(time.time()) - (trash.KEEP_DAYS + 1) * 86400
    meta_path.write_text(json.dumps(meta))
    assert sorted(item["name"] for item in listing(client, alice)) == ["b.txt", "c.txt"]
    monkeypatch.setattr(trash, "MAX_ITEMS", 1)
    put(client, alice, "d.txt")
    client.delete("/entries", params={"path": "/d.txt"}, headers=alice)
    assert [item["name"] for item in listing(client, alice)] == ["d.txt"]


def test_the_trash_does_not_count_for_the_quota_and_a_bad_id_is_refused(client, alice):
    put(client, alice, "a.txt", data=b"12345")
    client.delete("/entries", params={"path": "/a.txt"}, headers=alice)
    assert client.get("/entries", headers=alice).json()["usage"]["usedBytes"] == 0
    for bad in ("../x", "zz", "", "0" * 16 + "0"):
        assert client.post("/trash/restore", json={"id": bad}, headers=alice).status_code == 404


def test_the_trash_needs_a_session_and_goes_with_the_account(client, alice):
    assert client.get("/trash").status_code == 401
    assert client.post("/trash/restore", json={"id": "0" * 16}).status_code == 401
    put(client, alice, "a.txt")
    client.delete("/entries", params={"path": "/a.txt"}, headers=alice)
    assert (data_dir() / "trash" / "1").is_dir()
    from api.file.store import erase_user

    erase_user(1)
    assert not (data_dir() / "trash" / "1").exists()
