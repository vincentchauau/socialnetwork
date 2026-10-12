import io
import threading
from pathlib import Path

import pytest
from PIL import Image

from app import images
from app.images import ImageBusyError, InvalidImageError, process_image
from app.main import MAX_INT64
from app.storage import PhotoStorage

from .conftest import ALICE, BOB, make_image, upload


def test_upload_without_content_length_is_refused(client):
    def chunks():
        yield b"x" * 10

    response = client.post("/photos", content=chunks(), headers={**ALICE, "Content-Type": "multipart/form-data; boundary=b"})
    assert response.status_code == 411


def test_upload_declared_oversize_is_413(client):
    response = client.post("/photos", content=b"x", headers={**ALICE, "Content-Length": str(50 * 1024 * 1024)})
    assert response.status_code == 413


def test_photo_quota_boundary_and_delete_frees_slot(client):
    client.app.state.max_photos_per_user = 2
    first = upload(client)
    assert first.status_code == 201
    assert upload(client).status_code == 201
    blocked = upload(client)
    assert blocked.status_code == 409
    assert "limit" in blocked.json()["detail"].lower()
    assert upload(client, headers=BOB).status_code == 201  # other users unaffected
    assert client.delete(f"/photos/{first.json()['id']}", headers=ALICE).status_code == 204
    assert upload(client).status_code == 201


def test_quota_checked_before_saving_files(client, tmp_path):
    client.app.state.max_photos_per_user = 0
    assert upload(client).status_code == 409
    uploads = tmp_path / "uploads"
    assert not uploads.exists() or list(uploads.iterdir()) == []


@pytest.mark.parametrize("path", ["/photos/{n}", "/photos/{n}/like", "/photos/{n}/image"])
def test_ids_above_int64_are_422(client, path):
    method = client.put if path.endswith("/like") else client.get
    assert method(path.format(n=MAX_INT64 + 1), headers=ALICE).status_code == 422


def test_huge_cursor_and_comment_id_are_422(client):
    assert client.get(f"/photos?cursor={MAX_INT64 + 1}", headers=ALICE).status_code == 422
    assert client.get(f"/users/alice/photos?cursor={MAX_INT64 + 1}", headers=ALICE).status_code == 422
    assert client.delete(f"/comments/{MAX_INT64 + 1}", headers=ALICE).status_code == 422
    assert client.get(f"/photos?cursor={MAX_INT64}", headers=ALICE).status_code == 200


def test_delete_survives_unlink_failure(client, monkeypatch, caplog):
    photo = upload(client).json()

    def boom(self, missing_ok=False):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "unlink", boom)
    with caplog.at_level("WARNING"):
        response = client.delete(f"/photos/{photo['id']}", headers=ALICE)
    assert response.status_code == 204
    assert "Could not delete stored file" in caplog.text
    assert client.get(f"/photos/{photo['id']}", headers=ALICE).status_code == 404


def test_save_removes_image_when_thumbnail_write_fails(tmp_path, monkeypatch):
    storage = PhotoStorage(tmp_path / "up")
    real_write = Path.write_bytes

    def flaky(self, data):
        if self.name.endswith("_thumb.webp"):
            raise OSError("disk full")
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", flaky)
    with pytest.raises(OSError):
        storage.save(b"img", b"thumb", "png")
    assert list((tmp_path / "up").iterdir()) == []


def test_source_pixel_cap_is_lowered():
    assert images.MAX_SOURCE_PIXELS == 16_000_000
    big = io.BytesIO()
    Image.new("L", (4001, 4000)).save(big, format="PNG")
    with pytest.raises(InvalidImageError):
        process_image(big.getvalue())


@pytest.mark.parametrize("fmt,mode", [("JPEG", "RGB"), ("PNG", "RGBA"), ("GIF", "P"), ("WEBP", "RGB")])
def test_thumbnail_derived_for_each_format(fmt, mode):
    processed = process_image(make_image(fmt, (900, 600), mode))
    with Image.open(io.BytesIO(processed.thumb_data)) as thumb:
        assert max(thumb.size) == images.THUMB_DIMENSION
        assert thumb.format == "WEBP"


def test_large_jpeg_is_downscaled():
    processed = process_image(make_image("JPEG", (6000, 1000)))
    assert processed.width == images.MAX_DIMENSION


def test_busy_processor_fails_fast(monkeypatch, client):
    monkeypatch.setattr(images, "SLOT_TIMEOUT_SECONDS", 0.01)
    held = [images._slots.acquire() for _ in range(images.MAX_CONCURRENT_PROCESSING)]
    try:
        with pytest.raises(ImageBusyError):
            process_image(make_image())
        assert upload(client).status_code == 503
    finally:
        for _ in held:
            images._slots.release()
    assert upload(client).status_code == 201


def test_slot_released_after_invalid_image():
    for _ in range(images.MAX_CONCURRENT_PROCESSING + 1):
        with pytest.raises(InvalidImageError):
            process_image(b"not an image")
    assert isinstance(images._slots, type(threading.BoundedSemaphore()))
