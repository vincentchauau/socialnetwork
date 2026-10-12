import pytest

from tests.conftest import ALICE, BOB, auth_cookie, upload

CAROL = auth_cookie(3, "carol")


@pytest.fixture
def photo_id(client) -> int:
    return upload(client, headers=ALICE).json()["id"]


def test_like_is_idempotent_and_counted_once_per_user(client, photo_id):
    first = client.put(f"/photos/{photo_id}/like", headers=BOB)
    again = client.put(f"/photos/{photo_id}/like", headers=BOB)
    other = client.put(f"/photos/{photo_id}/like", headers=CAROL)
    assert first.json() == {"liked": True, "like_count": 1}
    assert again.json() == {"liked": True, "like_count": 1}
    assert other.json()["like_count"] == 2


def test_unlike_is_idempotent_and_only_removes_own_like(client, photo_id):
    client.put(f"/photos/{photo_id}/like", headers=BOB)
    client.put(f"/photos/{photo_id}/like", headers=CAROL)
    assert client.delete(f"/photos/{photo_id}/like", headers=BOB).json() == {"liked": False, "like_count": 1}
    assert client.delete(f"/photos/{photo_id}/like", headers=BOB).json() == {"liked": False, "like_count": 1}


def test_like_auth_and_missing_photo(client, photo_id):
    assert client.put(f"/photos/{photo_id}/like").status_code == 401
    assert client.delete(f"/photos/{photo_id}/like").status_code == 401
    assert client.put("/photos/999/like", headers=BOB).status_code == 404
    assert client.delete("/photos/999/like", headers=BOB).status_code == 404


def test_comment_lifecycle(client, photo_id):
    created = client.post(f"/photos/{photo_id}/comments", json={"content": "  nice  "}, headers=BOB)
    assert created.status_code == 201
    body = created.json()
    assert body["username"] == "bob" and body["content"] == "nice"
    assert set(body) == {"id", "photo_id", "username", "content", "created_at"}
    client.post(f"/photos/{photo_id}/comments", json={"content": "second"}, headers=CAROL)
    listed = client.get(f"/photos/{photo_id}/comments", headers=ALICE).json()
    assert [c["content"] for c in listed] == ["nice", "second"]


def test_comment_username_in_body_is_ignored(client, photo_id):
    response = client.post(
        f"/photos/{photo_id}/comments", json={"content": "x", "username": "alice", "user_id": 1}, headers=BOB
    )
    assert response.json()["username"] == "bob"


@pytest.mark.parametrize("payload", [{"content": ""}, {"content": "   "}, {"content": "x" * 501}, {}])
def test_comment_validation(client, photo_id, payload):
    assert client.post(f"/photos/{photo_id}/comments", json=payload, headers=BOB).status_code == 422


def test_comment_max_length_ok(client, photo_id):
    response = client.post(f"/photos/{photo_id}/comments", json={"content": "x" * 500}, headers=BOB)
    assert response.status_code == 201


def test_comment_auth_and_missing_photo(client, photo_id):
    assert client.post(f"/photos/{photo_id}/comments", json={"content": "x"}).status_code == 401
    assert client.get(f"/photos/{photo_id}/comments").status_code == 401
    assert client.post("/photos/999/comments", json={"content": "x"}, headers=BOB).status_code == 404
    assert client.get("/photos/999/comments", headers=BOB).status_code == 404
    assert client.get(f"/photos/{photo_id}/comments?limit=0", headers=BOB).status_code == 422


def test_comment_author_can_delete(client, photo_id):
    comment_id = client.post(f"/photos/{photo_id}/comments", json={"content": "x"}, headers=BOB).json()["id"]
    assert client.delete(f"/comments/{comment_id}", headers=BOB).status_code == 204
    assert client.get(f"/photos/{photo_id}/comments", headers=BOB).json() == []


def test_photo_owner_can_delete_any_comment(client, photo_id):
    comment_id = client.post(f"/photos/{photo_id}/comments", json={"content": "x"}, headers=BOB).json()["id"]
    assert client.delete(f"/comments/{comment_id}", headers=ALICE).status_code == 204


def test_stranger_cannot_delete_comment(client, photo_id):
    comment_id = client.post(f"/photos/{photo_id}/comments", json={"content": "x"}, headers=BOB).json()["id"]
    assert client.delete(f"/comments/{comment_id}", headers=CAROL).status_code == 403
    assert client.delete(f"/comments/{comment_id}").status_code == 401
    assert len(client.get(f"/photos/{photo_id}/comments", headers=BOB).json()) == 1


def test_delete_missing_comment(client):
    assert client.delete("/comments/999", headers=BOB).status_code == 404
    assert client.delete("/comments/0", headers=BOB).status_code == 422
