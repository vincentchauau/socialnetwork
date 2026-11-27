from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api.rally.video import parse_range, video_response


def test_parse_range_accepts_open_closed_and_suffix_ranges() -> None:
    assert parse_range("bytes=0-99", 1000) == (0, 99)
    assert parse_range("bytes=500-", 1000) == (500, 999)
    assert parse_range("bytes=-100", 1000) == (900, 999)


def test_parse_range_rejects_invalid_ranges() -> None:
    assert parse_range("bytes=900-100", 1000) is None
    assert parse_range("bytes=1000-", 1000) is None
    assert parse_range("items=0-1", 1000) is None
    assert parse_range("bytes=-", 1000) is None


def make_app(path: Path) -> FastAPI:
    app = FastAPI()

    @app.get("/video")
    def video(request: Request):
        return video_response(path, request)

    return app


def test_partial_content_returns_requested_bytes(tmp_path: Path) -> None:
    path = tmp_path / "clip.mp4"
    path.write_bytes(bytes(range(256)) * 4)
    client = TestClient(make_app(path))

    response = client.get("/video", headers={"Range": "bytes=10-19"})

    assert response.status_code == 206
    assert response.content == bytes(range(10, 20))
    assert response.headers["Content-Range"] == "bytes 10-19/1024"


def test_unsatisfiable_range_returns_416(tmp_path: Path) -> None:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"abc")

    response = TestClient(make_app(path)).get("/video", headers={"Range": "bytes=50-60"})

    assert response.status_code == 416
