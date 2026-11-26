"""Giving a file by a link, and finding files by name."""

import json
import time

from api.file import shares
from api.file.store import erase_user, files_root
from tests.file.test_files import mkdir, put


def share(client, headers, path="/a.txt", **body):
    return client.post("/share", json={"path": path, **body}, headers=headers)


def test_anybody_with_the_link_sees_what_the_file_is_and_downloads_it_without_signing_in(client, alice):
    put(client, alice, "report.txt", data=b"hello world")
    made = share(client, alice, "/report.txt")
    assert made.status_code == 201
    token = made.json()["token"]
    assert made.json()["page"] == f"/file/s/{token}" and made.json()["expiresAt"] is None and made.json()["size"] == 11

    info = client.get(f"/shared/{token}")  # no cookie
    assert info.status_code == 200 and (info.json()["name"], info.json()["size"]) == ("report.txt", 11)
    got = client.get(f"/shared/{token}/download")
    assert got.status_code == 200 and got.content == b"hello world"
    assert "attachment" in got.headers["content-disposition"] and got.headers["x-content-type-options"] == "nosniff"
    assert "path" not in info.json() and "user_id" not in info.json()  # nothing of where it is kept or whose it is


def test_only_a_file_of_the_person_can_be_shared(client, alice, bob):
    put(client, alice, "a.txt")
    mkdir(client, alice, "d")
    assert share(client, bob, "/a.txt").status_code == 404  # it is Alice's file: Bob has none of that name
    assert share(client, alice, "/d").status_code == 404  # a folder is not given
    assert share(client, alice, "/missing.txt").status_code == 404
    assert share(client, alice, "/../x").status_code == 404  # a path that leaves the tree finds nothing
    assert client.post("/share", json={"path": "/a.txt"}).status_code == 401


def test_a_new_link_replaces_the_old_one_and_the_owner_lists_and_takes_them_back(client, alice, bob):
    put(client, alice, "a.txt")
    first = share(client, alice).json()["token"]
    second = share(client, alice, days=7).json()
    assert client.get(f"/shared/{first}").status_code == 404 and client.get(f"/shared/{second['token']}").status_code == 200
    assert second["expiresAt"] is not None
    assert [item["token"] for item in client.get("/shares", headers=alice).json()["shares"]] == [second["token"]]
    assert client.get("/shares", headers=bob).json() == {"shares": []}
    assert client.delete(f"/share/{second['token']}", headers=bob).status_code == 404  # not his
    assert client.delete(f"/share/{second['token']}", headers=alice).status_code == 204
    assert client.get(f"/shared/{second['token']}").status_code == 404


def test_a_link_that_ran_out_or_whose_file_is_gone_or_moved_does_not_work(client, alice):
    put(client, alice, "a.txt")
    token = share(client, alice).json()["token"]
    record = shares.shares_dir() / f"{token}.json"
    data = json.loads(record.read_text())
    record.write_text(json.dumps({**data, "expiresAt": time.time() - 1}))
    assert client.get(f"/shared/{token}").status_code == 404
    record.write_text(json.dumps({**data, "expiresAt": None}))
    assert client.get(f"/shared/{token}").status_code == 200
    client.delete("/entries", params={"path": "/a.txt"}, headers=alice)  # to the trash: the link does not follow it
    assert client.get(f"/shared/{token}").status_code == 404
    assert client.get("/shares", headers=alice).json() == {"shares": []}


def test_a_token_that_is_not_one_cannot_read_anything_else(client, alice):
    put(client, alice, "a.txt")
    share(client, alice)
    assert client.get("/shared/short").status_code == 422
    assert client.get("/shared/" + "x" * 30).status_code == 404
    assert client.get("/shared/..%2F..%2Fetc%2Fpasswd" + "0" * 16).status_code in (404, 422)
    assert client.get("/shared/" + "../" * 6 + "a" * 16).status_code in (404, 422)


def test_a_person_shares_a_limited_number_of_files_and_the_links_go_with_the_account(client, alice, monkeypatch):
    monkeypatch.setattr(shares, "MAX_SHARES_PER_USER", 2)
    for name in ("1.txt", "2.txt", "3.txt"):
        put(client, alice, name)
    assert share(client, alice, "/1.txt").status_code == 201 and share(client, alice, "/2.txt").status_code == 201
    assert share(client, alice, "/3.txt").status_code == 409
    assert share(client, alice, "/1.txt").status_code == 201  # a new link for a file that has one is not one more
    erase_user(1)
    assert client.get("/shares", headers=alice).json() == {"shares": []}
    assert list(shares.shares_dir().glob("*.json")) == []


def test_the_days_are_limited(client, alice):
    put(client, alice, "a.txt")
    assert share(client, alice, days=0).status_code == 422 and share(client, alice, days=366).status_code == 422


