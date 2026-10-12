from tests.conftest import MP4_BYTES, WEBM_BYTES, auth_cookie, upload


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_mp4_returns_metadata_without_internals(client, upload_dir):
    response = upload(client, tags=["Funny", " cats "], extra={"description": "d"})
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "My clip"
    assert body["owner"] == "alice"
    assert body["tags"] == ["funny", "cats"]
    assert body["content_type"] == "video/mp4"
    assert body["size_bytes"] == len(MP4_BYTES)
    assert body["views"] == 0
    assert "file_name" not in body and "path" not in body
    stored = list(upload_dir.iterdir())
    assert len(stored) == 1
    assert stored[0].name != "clip.mp4" and stored[0].suffix == ".mp4"


def test_upload_webm(client):
    response = upload(client, content=WEBM_BYTES, filename="x.bin")
    assert response.status_code == 201
    assert response.json()["content_type"] == "video/webm"


def test_upload_requires_auth(client):
    response = client.post(
        "/videos",
        data={"title": "t", "rights_confirmed": "true"},
        files={"file": ("a.mp4", MP4_BYTES)},
    )
    assert response.status_code == 401


def test_upload_requires_rights_confirmation(client, upload_dir):
    assert upload(client, rights="false").status_code == 422
    assert not upload_dir.exists() or not list(upload_dir.iterdir())


def test_upload_missing_rights_field(client):
    response = client.post(
        "/videos",
        headers=auth_cookie(),
        data={"title": "t"},
        files={"file": ("a.mp4", MP4_BYTES)},
    )
    assert response.status_code == 422


def test_upload_rejects_wrong_content_even_with_mp4_name(client, upload_dir):
    response = upload(client, content=b"<html>not a video at all</html>", filename="a.mp4")
    assert response.status_code == 415
    assert not list(upload_dir.iterdir())


def test_upload_rejects_empty_file(client):
    assert upload(client, content=b"").status_code == 422


def test_upload_rejects_oversize_and_removes_partial(client, upload_dir):
    big = MP4_BYTES + b"\x00" * (1024 * 1024)
    response = upload(client, content=big)
    assert response.status_code == 413
    assert not list(upload_dir.iterdir())


def test_upload_rejects_oversize_content_length_early(client):
    response = client.post(
        "/videos",
        headers={**auth_cookie(), "Content-Length": str(50 * 1024 * 1024)},
        data={"title": "t", "rights_confirmed": "true"},
        files={"file": ("a.mp4", MP4_BYTES)},
    )
    assert response.status_code == 413


def test_upload_validation(client):
    assert upload(client, title="").status_code == 422
    assert upload(client, title="   ").status_code == 422
    assert upload(client, title="x" * 121).status_code == 422
    assert upload(client, extra={"description": "x" * 2001}).status_code == 422
    assert upload(client, tags=[str(i) for i in range(11)]).status_code == 422
    assert upload(client, tags=["x" * 31]).status_code == 422
    assert upload(client, tags=["a,b"]).status_code == 422
    assert upload(client, tags=[" "]).status_code == 422


def test_upload_dedupes_tags(client):
    response = upload(client, tags=["a", "A", "b"])
    assert response.json()["tags"] == ["a", "b"]


def test_username_comes_from_token(client):
    response = upload(client, user_id=5, username="bob", extra={"owner": "mallory"})
    assert response.json()["owner"] == "bob"


def test_get_video_requires_auth_and_404(client):
    assert client.get("/videos/1").status_code == 401
    assert client.get("/videos/999", headers=auth_cookie()).status_code == 404
    assert client.get("/videos/abc", headers=auth_cookie()).status_code == 422


def test_get_video_counts_view_once_per_user(client):
    video_id = upload(client).json()["id"]
    for _ in range(3):
        client.get(f"/videos/{video_id}", headers=auth_cookie(2, "bob"))
    body = client.get(f"/videos/{video_id}", headers=auth_cookie(3, "carol")).json()
    assert body["views"] == 2
    assert body["in_watchlist"] is False
    assert body["progress_seconds"] == 0


def test_catalog_requires_auth(client):
    assert client.get("/videos").status_code == 401


def test_catalog_newest_first_and_cursor(client):
    ids = [upload(client, title=f"clip {i}").json()["id"] for i in range(5)]
    first = client.get("/videos?limit=2", headers=auth_cookie()).json()
    assert [v["id"] for v in first["items"]] == [ids[4], ids[3]]
    assert first["next_cursor"] == ids[3]
    second = client.get(f"/videos?limit=2&cursor={first['next_cursor']}", headers=auth_cookie()).json()
    assert [v["id"] for v in second["items"]] == [ids[2], ids[1]]
    third = client.get(f"/videos?limit=2&cursor={second['next_cursor']}", headers=auth_cookie()).json()
    assert [v["id"] for v in third["items"]] == [ids[0]]
    assert third["next_cursor"] is None


def test_catalog_limit_bounds(client):
    assert client.get("/videos?limit=51", headers=auth_cookie()).status_code == 422
    assert client.get("/videos?limit=0", headers=auth_cookie()).status_code == 422
    assert client.get("/videos?cursor=0", headers=auth_cookie()).status_code == 422


def test_catalog_search_and_tag(client):
    upload(client, title="Mountain Hike", tags=["outdoors"])
    upload(client, title="Cooking pasta", tags=["food", "italy"])
    cookie = auth_cookie()
    by_title = client.get("/videos?q=hike", headers=cookie).json()["items"]
    assert [v["title"] for v in by_title] == ["Mountain Hike"]
    by_tag_search = client.get("/videos?q=ital", headers=cookie).json()["items"]
    assert [v["title"] for v in by_tag_search] == ["Cooking pasta"]
    by_tag = client.get("/videos?tag=FOOD", headers=cookie).json()["items"]
    assert [v["title"] for v in by_tag] == ["Cooking pasta"]
    assert client.get("/videos?tag=foo", headers=cookie).json()["items"] == []


def test_search_treats_wildcards_literally(client):
    upload(client, title="100% real")
    upload(client, title="other")
    items = client.get("/videos?q=%25", headers=auth_cookie()).json()["items"]
    assert [v["title"] for v in items] == ["100% real"]
    assert client.get("/videos?q=_", headers=auth_cookie()).json()["items"] == []


def test_delete_owner_only_and_removes_file(client, upload_dir):
    video_id = upload(client).json()["id"]
    assert client.delete(f"/videos/{video_id}").status_code == 401
    forbidden = client.delete(f"/videos/{video_id}", headers=auth_cookie(2, "bob"))
    assert forbidden.status_code == 403
    assert len(list(upload_dir.iterdir())) == 1
    assert client.delete(f"/videos/{video_id}", headers=auth_cookie()).status_code == 204
    assert not list(upload_dir.iterdir())
    assert client.get(f"/videos/{video_id}", headers=auth_cookie()).status_code == 404
    assert client.delete(f"/videos/{video_id}", headers=auth_cookie()).status_code == 404


def test_delete_cleans_related_rows(client):
    video_id = upload(client).json()["id"]
    cookie = auth_cookie(2, "bob")
    client.put(f"/videos/{video_id}/watchlist", headers=cookie)
    client.put(f"/videos/{video_id}/progress", headers=cookie, json={"seconds": 3})
    client.delete(f"/videos/{video_id}", headers=auth_cookie())
    assert client.get("/me/watchlist", headers=cookie).json() == []
    assert client.get("/me/history", headers=cookie).json() == []
