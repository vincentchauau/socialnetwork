from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.file import files

LIMIT = files.MAX_FILE_BYTES + 64 * 1024


def _mounted(client) -> TestClient:
    parent = FastAPI()
    parent.mount("/file", client.app)
    return TestClient(parent)


def test_oversized_upload_is_refused_before_auth_when_mounted(client):
    body = b"x" * (LIMIT + 1)
    response = _mounted(client).post("/file/upload", content=body)
    assert response.status_code == 413


def test_upload_without_content_length_is_refused_when_mounted(client):
    def chunks():
        yield b"x"

    response = _mounted(client).post("/file/upload", content=chunks())
    assert response.status_code == 411
