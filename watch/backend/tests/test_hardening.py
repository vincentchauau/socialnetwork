from pathlib import Path

from tests.conftest import MP4_BYTES, auth_cookie, upload

from app.routes_videos import MAX_INT64
from app.storage import sniff_video_type

ALICE = auth_cookie(1, "alice")


def test_upload_without_content_length_is_411(client):
    def chunks():
        yield b"x" * 10

    response = client.post(
        "/videos", content=chunks(), headers={**ALICE, "Content-Type": "multipart/form-data; boundary=b"}
    )
    assert response.status_code == 411


def test_video_count_quota_boundary_and_delete_frees(client, upload_dir):
    client.app.state.max_videos_per_user = 2
    first = upload(client)
    assert first.status_code == 201
    assert upload(client).status_code == 201
    blocked = upload(client)
    assert blocked.status_code == 409
    assert "limit" in blocked.json()["detail"].lower()
    assert len(list(upload_dir.iterdir())) == 2  # nothing saved for the refused upload
    assert upload(client, user_id=2, username="bob").status_code == 201
    assert client.delete(f"/videos/{first.json()['id']}", headers=ALICE).status_code == 204
    assert upload(client).status_code == 201


def test_byte_quota_boundary(client):
    size = len(MP4_BYTES)
    client.app.state.max_user_bytes = size * 2
    assert upload(client).status_code == 201
    assert upload(client).status_code == 201  # exactly at the limit afterwards
    blocked = upload(client)
    assert blocked.status_code == 409
    assert "quota" in blocked.json()["detail"].lower()


def test_byte_quota_caps_a_single_large_upload(client, upload_dir):
    client.app.state.max_user_bytes = len(MP4_BYTES) - 1
    response = upload(client)
    assert response.status_code == 409
    assert list(upload_dir.iterdir()) == []


def test_delete_frees_byte_quota(client):
    client.app.state.max_user_bytes = len(MP4_BYTES)
    video = upload(client)
    assert video.status_code == 201
    assert upload(client).status_code == 409
    assert client.delete(f"/videos/{video.json()['id']}", headers=ALICE).status_code == 204
    assert upload(client).status_code == 201


def test_unknown_mp4_brand_is_rejected(client):
    content = b"\x00\x00\x00\x18ftypzzzz\x00\x00\x00\x00zzzzisom" + bytes(64)
    assert upload(client, content=content).status_code == 415
    assert sniff_video_type(MP4_BYTES[:12]) == "video/mp4"
    assert sniff_video_type(b"\x00\x00\x00\x18ftypisom") == "video/mp4"


def test_ids_and_cursor_above_int64_are_422(client):
    assert client.get(f"/videos/{MAX_INT64 + 1}", headers=ALICE).status_code == 422
    assert client.get(f"/videos/{MAX_INT64 + 1}/stream", headers=ALICE).status_code == 422
    assert client.put(f"/videos/{MAX_INT64 + 1}/watchlist", headers=ALICE).status_code == 422
    assert client.get(f"/videos?cursor={MAX_INT64 + 1}", headers=ALICE).status_code == 422
    assert client.get(f"/videos?cursor={MAX_INT64}", headers=ALICE).status_code == 200


def test_huge_range_header_never_500(client):
    video = upload(client).json()
    url = f"/videos/{video['id']}/stream"
    for header in ("bytes=" + "9" * 5000 + "-", "bytes=0-" + "9" * 5000, "bytes=-" + "9" * 5000):
        response = client.get(url, headers={**ALICE, "Range": header})
        assert response.status_code in (200, 416)


def test_delete_survives_unlink_failure(client, monkeypatch, caplog):
    video = upload(client).json()

    def boom(self, missing_ok=False):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "unlink", boom)
    with caplog.at_level("WARNING"):
        response = client.delete(f"/videos/{video['id']}", headers=ALICE)
    assert response.status_code == 204
    assert "Could not delete stored video" in caplog.text
    assert client.get(f"/videos/{video['id']}", headers=ALICE).status_code == 404
