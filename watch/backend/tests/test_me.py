from tests.conftest import auth_cookie, upload

BOB = auth_cookie(2, "bob")


def _video(client, title: str = "clip") -> int:
    return upload(client, title=title).json()["id"]


def test_progress_requires_auth_and_video(client):
    video_id = _video(client)
    assert client.put(f"/videos/{video_id}/progress", json={"seconds": 1}).status_code == 401
    missing = client.put("/videos/99/progress", headers=BOB, json={"seconds": 1})
    assert missing.status_code == 404


def test_progress_upsert_per_user(client):
    video_id = _video(client)
    url = f"/videos/{video_id}/progress"
    assert client.put(url, headers=BOB, json={"seconds": 12.5}).json()["seconds"] == 12.5
    assert client.put(url, headers=BOB, json={"seconds": 30}).json()["seconds"] == 30
    client.put(url, headers=auth_cookie(), json={"seconds": 4})
    assert client.get(f"/videos/{video_id}", headers=BOB).json()["progress_seconds"] == 30
    assert client.get(f"/videos/{video_id}", headers=auth_cookie()).json()["progress_seconds"] == 4


def test_progress_validation(client):
    video_id = _video(client)
    url = f"/videos/{video_id}/progress"
    assert client.put(url, headers=BOB, json={"seconds": -1}).status_code == 422
    assert client.put(url, headers=BOB, json={"seconds": 10**9}).status_code == 422
    assert client.put(url, headers=BOB, json={"seconds": "x"}).status_code == 422
    assert client.put(url, headers=BOB, json={}).status_code == 422


def test_history_most_recent_first(client):
    first, second = _video(client, "one"), _video(client, "two")
    client.put(f"/videos/{first}/progress", headers=BOB, json={"seconds": 5})
    client.put(f"/videos/{second}/progress", headers=BOB, json={"seconds": 8})
    client.put(f"/videos/{first}/progress", headers=BOB, json={"seconds": 9})
    history = client.get("/me/history", headers=BOB).json()
    assert [(h["video"]["title"], h["seconds"]) for h in history] == [("one", 9), ("two", 8)]
    assert client.get("/me/history", headers=auth_cookie()).json() == []
    assert client.get("/me/history").status_code == 401


def test_history_limit_validation(client):
    assert client.get("/me/history?limit=0", headers=BOB).status_code == 422
    assert client.get("/me/history?limit=51", headers=BOB).status_code == 422


def test_watchlist_add_idempotent_remove(client):
    first, second = _video(client, "one"), _video(client, "two")
    for video_id in (first, second, first):
        assert client.put(f"/videos/{video_id}/watchlist", headers=BOB).status_code == 204
    items = client.get("/me/watchlist", headers=BOB).json()
    assert [v["title"] for v in items] == ["two", "one"]
    assert client.get(f"/videos/{first}", headers=BOB).json()["in_watchlist"] is True
    assert client.delete(f"/videos/{first}/watchlist", headers=BOB).status_code == 204
    assert client.delete(f"/videos/{first}/watchlist", headers=BOB).status_code == 204
    assert [v["title"] for v in client.get("/me/watchlist", headers=BOB).json()] == ["two"]


def test_watchlist_is_private_and_guarded(client):
    video_id = _video(client)
    client.put(f"/videos/{video_id}/watchlist", headers=BOB)
    assert client.get("/me/watchlist", headers=auth_cookie()).json() == []
    assert client.put(f"/videos/{video_id}/watchlist").status_code == 401
    assert client.get("/me/watchlist").status_code == 401
    assert client.put("/videos/99/watchlist", headers=BOB).status_code == 404
    assert client.delete("/videos/99/watchlist", headers=BOB).status_code == 404
