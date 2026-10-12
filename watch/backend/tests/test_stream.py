import pytest
from tests.conftest import MP4_BYTES, WEBM_BYTES, auth_cookie, upload

from app.ranges import RangeNotSatisfiableError, parse_range

SIZE = len(MP4_BYTES)


def _video(client, content: bytes = MP4_BYTES) -> int:
    return upload(client, content=content).json()["id"]


def test_stream_requires_auth_and_404(client):
    assert client.get("/videos/1/stream").status_code == 401
    assert client.get("/videos/9/stream", headers=auth_cookie()).status_code == 404


def test_full_stream_headers(client):
    video_id = _video(client)
    response = client.get(f"/videos/{video_id}/stream", headers=auth_cookie())
    assert response.status_code == 200
    assert response.content == MP4_BYTES
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-length"] == str(SIZE)


def test_webm_content_type(client):
    video_id = _video(client, WEBM_BYTES)
    response = client.get(f"/videos/{video_id}/stream", headers=auth_cookie())
    assert response.headers["content-type"] == "video/webm"


def test_partial_range(client):
    video_id = _video(client)
    response = client.get(
        f"/videos/{video_id}/stream", headers={**auth_cookie(), "Range": "bytes=10-19"}
    )
    assert response.status_code == 206
    assert response.content == MP4_BYTES[10:20]
    assert response.headers["content-range"] == f"bytes 10-19/{SIZE}"
    assert response.headers["content-length"] == "10"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_open_ended_and_suffix_range(client):
    video_id = _video(client)
    cookie = auth_cookie()
    open_end = client.get(f"/videos/{video_id}/stream", headers={**cookie, "Range": "bytes=100-"})
    assert open_end.status_code == 206
    assert open_end.content == MP4_BYTES[100:]
    suffix = client.get(f"/videos/{video_id}/stream", headers={**cookie, "Range": "bytes=-16"})
    assert suffix.content == MP4_BYTES[-16:]
    assert suffix.headers["content-range"] == f"bytes {SIZE - 16}-{SIZE - 1}/{SIZE}"


def test_unsatisfiable_range_is_416(client):
    video_id = _video(client)
    response = client.get(
        f"/videos/{video_id}/stream", headers={**auth_cookie(), "Range": f"bytes={SIZE}-"}
    )
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{SIZE}"


def test_ignored_range_forms_serve_full_file(client):
    video_id = _video(client)
    for value in ("items=0-5", "bytes=abc", "bytes=5-2", "bytes=0-1,4-5", "bytes=-"):
        response = client.get(
            f"/videos/{video_id}/stream", headers={**auth_cookie(), "Range": value}
        )
        assert response.status_code == 200, value
        assert response.content == MP4_BYTES


def test_stream_404_when_file_missing(client, upload_dir):
    video_id = _video(client)
    for path in upload_dir.iterdir():
        path.unlink()
    assert client.get(f"/videos/{video_id}/stream", headers=auth_cookie()).status_code == 404


def test_end_clamped_to_size():
    assert parse_range("bytes=0-999999", 100) == (0, 99)
    assert parse_range("bytes=-500", 100) == (0, 99)
    assert parse_range(None, 100) is None


def test_zero_suffix_unsatisfiable():
    with pytest.raises(RangeNotSatisfiableError):
        parse_range("bytes=-0", 100)
