import io
import os

import pytest
from PIL import Image

from app.images import MAX_DIMENSION, MAX_UPLOAD_BYTES, InvalidImageError, process_image
from app.storage import PhotoStorage
from tests.conftest import ALICE, BOB, make_image, upload


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_happy_path(client):
    response = upload(client, caption="  hello  ")
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "alice"
    assert body["caption"] == "hello"
    assert (body["like_count"], body["comment_count"], body["liked_by_me"]) == (0, 0, False)
    assert body["is_mine"] is True
    assert "image_name" not in body and "user_id" not in body


@pytest.mark.parametrize("fmt,ctype", [("JPEG", "image/jpeg"), ("PNG", "image/png"),
                                       ("WEBP", "image/webp"), ("GIF", "image/gif")])
def test_serves_image_and_thumb_with_security_headers(client, fmt, ctype):
    photo = upload(client, data=make_image(fmt, (800, 600))).json()
    image = client.get(photo["image_url"], headers=ALICE)
    assert image.status_code == 200
    assert image.headers["content-type"] == ctype
    assert image.headers["x-content-type-options"] == "nosniff"
    assert "max-age" in image.headers["cache-control"]
    thumb = client.get(photo["thumb_url"], headers=BOB)
    assert thumb.headers["content-type"] == "image/webp"
    assert max(Image.open(io.BytesIO(thumb.content)).size) <= 400


def test_image_requires_auth(client):
    photo = upload(client).json()
    assert client.get(photo["image_url"]).status_code == 401
    assert client.get(photo["thumb_url"]).status_code == 401


def test_upload_requires_auth(client):
    assert client.post("/photos", files={"file": ("a.png", make_image())}).status_code == 401


def test_rejects_non_image_even_with_image_name(client):
    response = upload(client, data=b"<html>not an image</html>", name="evil.png")
    assert response.status_code == 422


def test_rejects_disallowed_format(client):
    assert upload(client, data=make_image("BMP")).status_code == 422


def test_rejects_empty_file(client):
    assert upload(client, data=b"").status_code == 422


def test_rejects_oversized_file(client):
    assert upload(client, data=b"0" * (MAX_UPLOAD_BYTES + 1)).status_code == 413


def test_rejects_missing_file(client):
    assert client.post("/photos", data={"caption": "x"}, headers=ALICE).status_code == 422


def test_rejects_long_caption(client):
    assert upload(client, caption="x" * 501).status_code == 422
    assert upload(client, caption="x" * 500).status_code == 201


def test_blank_caption_becomes_null(client):
    assert upload(client, caption="   ").json()["caption"] is None


def test_exif_is_stripped_and_dimensions_capped(client):
    source = Image.new("RGB", (5000, 100), "blue")
    exif = Image.Exif()
    exif[0x010E] = "secret description"
    buffer = io.BytesIO()
    source.save(buffer, format="JPEG", exif=exif)
    photo = upload(client, data=buffer.getvalue()).json()
    assert photo["width"] == MAX_DIMENSION
    stored = Image.open(io.BytesIO(client.get(photo["image_url"], headers=ALICE).content))
    assert len(stored.getexif()) == 0
    assert max(stored.size) <= MAX_DIMENSION


def test_client_filename_is_never_used(client, tmp_path):
    upload(client, name="../../evil.png")
    names = os.listdir(client.app.state.storage._root)
    assert len(names) == 2
    assert all("evil" not in name and ".." not in name for name in names)


def test_alpha_png_and_animated_gif_are_processed():
    rgba = process_image(make_image("PNG", mode="RGBA"))
    assert rgba.content_type == "image/png"
    frames = []
    for color in ("red", "blue"):
        frames.append(Image.new("RGB", (10, 10), color))
    buffer = io.BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:])
    assert process_image(buffer.getvalue()).content_type == "image/gif"


def test_decompression_bomb_rejected(monkeypatch):
    monkeypatch.setattr("app.images.MAX_SOURCE_PIXELS", 10)
    with pytest.raises(InvalidImageError):
        process_image(make_image("PNG", (100, 100)))


def test_truncated_image_rejected():
    with pytest.raises(InvalidImageError):
        process_image(make_image("PNG", (200, 200))[:80])


def test_feed_pagination_newest_first(client):
    ids = [upload(client, caption=str(i)).json()["id"] for i in range(5)]
    first = client.get("/photos?limit=2", headers=BOB).json()
    assert [p["id"] for p in first["items"]] == ids[::-1][:2]
    assert first["next_cursor"] == first["items"][-1]["id"]
    second = client.get(f"/photos?limit=2&cursor={first['next_cursor']}", headers=BOB).json()
    assert [p["id"] for p in second["items"]] == ids[::-1][2:4]
    last = client.get(f"/photos?limit=2&cursor={second['next_cursor']}", headers=BOB).json()
    assert [p["id"] for p in last["items"]] == [ids[0]]
    assert last["next_cursor"] is None


def test_feed_empty(client):
    assert client.get("/photos", headers=ALICE).json() == {"items": [], "next_cursor": None}


@pytest.mark.parametrize("query", ["limit=0", "limit=51", "cursor=0", "limit=abc"])
def test_feed_validation(client, query):
    assert client.get(f"/photos?{query}", headers=ALICE).status_code == 422


def test_feed_requires_auth(client):
    assert client.get("/photos").status_code == 401


def test_feed_counts_and_liked_by_me(client):
    photo_id = upload(client).json()["id"]
    client.put(f"/photos/{photo_id}/like", headers=BOB)
    client.post(f"/photos/{photo_id}/comments", json={"content": "hi"}, headers=BOB)
    as_bob = client.get("/photos", headers=BOB).json()["items"][0]
    as_alice = client.get("/photos", headers=ALICE).json()["items"][0]
    assert (as_bob["like_count"], as_bob["comment_count"], as_bob["liked_by_me"]) == (1, 1, True)
    assert as_alice["liked_by_me"] is False and as_bob["is_mine"] is False


def test_get_photo_and_not_found(client):
    photo_id = upload(client).json()["id"]
    assert client.get(f"/photos/{photo_id}", headers=BOB).json()["id"] == photo_id
    assert client.get("/photos/999", headers=BOB).status_code == 404
    assert client.get("/photos/0", headers=BOB).status_code == 422
    assert client.get("/photos/1").status_code == 401


def test_delete_owner_removes_files_and_related_rows(client):
    photo_id = upload(client).json()["id"]
    client.put(f"/photos/{photo_id}/like", headers=BOB)
    client.post(f"/photos/{photo_id}/comments", json={"content": "x"}, headers=BOB)
    storage = client.app.state.storage
    assert len(os.listdir(storage._root)) == 2
    assert client.delete(f"/photos/{photo_id}", headers=ALICE).status_code == 204
    assert os.listdir(storage._root) == []
    assert client.get(f"/photos/{photo_id}", headers=ALICE).status_code == 404
    assert client.get(f"/photos/{photo_id}/comments", headers=ALICE).status_code == 404


def test_delete_requires_ownership_and_auth(client):
    photo_id = upload(client).json()["id"]
    assert client.delete(f"/photos/{photo_id}", headers=BOB).status_code == 403
    assert client.delete(f"/photos/{photo_id}").status_code == 401
    assert client.delete("/photos/999", headers=ALICE).status_code == 404
    assert client.get(f"/photos/{photo_id}", headers=ALICE).status_code == 200


def test_image_404_when_file_missing(client):
    photo = upload(client).json()
    storage = client.app.state.storage
    for name in os.listdir(storage._root):
        os.remove(storage._root / name)
    assert client.get(photo["image_url"], headers=ALICE).status_code == 404
    assert client.get("/photos/999/image", headers=ALICE).status_code == 404


def test_user_photos(client):
    upload(client, headers=ALICE)
    upload(client, headers=BOB)
    upload(client, headers=ALICE)
    items = client.get("/users/alice/photos", headers=BOB).json()["items"]
    assert [p["username"] for p in items] == ["alice", "alice"]
    assert client.get("/users/nobody/photos", headers=BOB).json()["items"] == []
    assert client.get("/users/alice/photos").status_code == 401
    assert client.get("/users/alice/photos?limit=1", headers=BOB).json()["next_cursor"] is not None


def test_storage_rejects_traversal(tmp_path):
    storage = PhotoStorage(tmp_path)
    for bad in ("../x.png", "a/b.png", "..\\x.png", "name.exe", ""):
        with pytest.raises(ValueError):
            storage.resolve(bad)
