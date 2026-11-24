"""Replacing a file keeps what it was, and a version can be put back."""

import json
import time

from api.file import versions
from api.file.store import data_dir, erase_user, files_root
from tests.file.test_files import mkdir, put


def replace(client, headers, name="a.txt", data=b"new", path="/"):
    return client.post("/upload", params={"path": path, "replace": "true"}, files={"file": (name, data, "text/plain")}, headers=headers)


def kept(client, headers, path="/a.txt"):
    return client.get("/versions", params={"path": path}, headers=headers).json()["versions"]


def test_a_name_that_is_taken_is_refused_unless_the_file_is_replaced(client, alice):
    put(client, alice, "a.txt", data=b"old")
    assert put(client, alice, "a.txt", data=b"new").status_code == 409
    done = replace(client, alice)
    assert done.status_code == 201 and done.json() == {"name": "a.txt", "size": 3, "replaced": True}
    assert (files_root(1) / "a.txt").read_bytes() == b"new"
    [version] = kept(client, alice)
    assert version["size"] == 3 and (versions.versions_dir(1) / version["id"] / versions.ITEM).read_bytes() == b"old"


def test_replacing_a_file_that_is_not_there_just_makes_it(client, alice):
    done = replace(client, alice, "fresh.txt", b"x")
    assert done.status_code == 201 and done.json() == {"name": "fresh.txt", "size": 1}
    assert kept(client, alice, "/fresh.txt") == []


def test_a_version_comes_back_and_the_file_it_replaces_is_kept_so_it_can_be_undone(client, alice):
    mkdir(client, alice, "d")
    put(client, alice, "a.txt", data=b"one", path="/d")
    replace(client, alice, data=b"two", path="/d")
    replace(client, alice, data=b"three", path="/d")
    assert [item["size"] for item in kept(client, alice, "/d/a.txt")] == [3, 3]
    first = kept(client, alice, "/d/a.txt")[-1]  # the oldest: "one"
    back = client.post("/versions/restore", json={"id": first["id"]}, headers=alice)
    assert back.status_code == 200 and back.json() == {"name": "a.txt", "path": "/d"}
    assert (files_root(1) / "d" / "a.txt").read_bytes() == b"one"
    contents = sorted((versions.versions_dir(1) / item["id"] / versions.ITEM).read_bytes() for item in kept(client, alice, "/d/a.txt"))
    assert contents == [b"three", b"two"]  # "three" was the file and is now a version; the restored one is no longer one


def test_a_version_of_a_file_that_was_deleted_makes_the_file_again(client, alice):
    put(client, alice, "a.txt", data=b"old")
    replace(client, alice, data=b"new")
    client.delete("/entries", params={"path": "/a.txt"}, headers=alice)
    [version] = kept(client, alice)
    assert client.post("/versions/restore", json={"id": version["id"]}, headers=alice).status_code == 200
    assert (files_root(1) / "a.txt").read_bytes() == b"old"


def test_only_the_last_five_versions_of_a_file_are_kept(client, alice):
    put(client, alice, "a.txt", data=b"0")
    for number in range(1, 8):
        replace(client, alice, data=str(number).encode())
    assert len(kept(client, alice)) == versions.PER_FILE
    contents = [(versions.versions_dir(1) / item["id"] / versions.ITEM).read_bytes() for item in kept(client, alice)]
    assert contents == [b"6", b"5", b"4", b"3", b"2"]  # the newest first; "0" and "1" went


def test_what_is_too_old_goes_and_too_many_bytes_push_out_the_oldest(client, alice, monkeypatch):
    put(client, alice, "a.txt", data=b"0")
    replace(client, alice, data=b"1")
    [version] = kept(client, alice)
    path = versions.versions_dir(1) / version["id"] / versions.META
    meta = json.loads(path.read_text())
    path.write_text(json.dumps({**meta, "savedAt": int(time.time()) - (versions.KEEP_DAYS + 1) * 86400}))
    assert kept(client, alice) == []
    monkeypatch.setattr(versions, "MAX_BYTES", 5)
    for number in range(3):
        replace(client, alice, data=b"abcd")  # each kept version is 4 bytes: only one fits
    assert len(kept(client, alice)) == 1


def test_a_version_is_a_persons_own_and_can_be_dropped(client, alice, bob):
    put(client, alice, "a.txt", data=b"old")
    replace(client, alice)
    [version] = kept(client, alice)
    assert kept(client, bob) == []
    assert client.post("/versions/restore", json={"id": version["id"]}, headers=bob).status_code == 404
    assert client.delete("/versions", params={"id": version["id"]}, headers=bob).status_code == 404
    assert client.delete("/versions", params={"id": version["id"]}, headers=alice).status_code == 204
    assert kept(client, alice) == []
    for bad in ("../x", "zz", "0" * 16):
        assert client.post("/versions/restore", json={"id": bad}, headers=alice).status_code == 404


def test_replacing_respects_the_quota_and_a_failed_replace_keeps_nothing_new(client, alice, monkeypatch):
    from api.file import files

    put(client, alice, "a.txt", data=b"x" * 100)
    monkeypatch.setattr(files, "QUOTA_BYTES", 150)
    assert replace(client, alice, data=b"y" * 120).status_code == 201  # 100 goes out, 120 comes in: 120 fits
    assert replace(client, alice, data=b"z" * 200).status_code == 413
    assert (files_root(1) / "a.txt").read_bytes() == b"y" * 120
    assert len(kept(client, alice)) == 1  # the refused one left no version


def test_the_versions_go_with_the_account_and_there_is_no_replace_in_the_data_area(client, alice):
    put(client, alice, "a.txt", data=b"old")
    replace(client, alice)
    assert (data_dir() / "versions" / "1").is_dir()
    erase_user(1)
    assert not (data_dir() / "versions" / "1").exists()
    assert client.get("/versions", params={"path": "/a.txt"}).status_code == 401
