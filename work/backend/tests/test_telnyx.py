import base64
import json
import logging
import time

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import telnyx
from app.main import create_app
from fastapi.testclient import TestClient
from tests.conftest import auth_cookie

SECRET_API_KEY = "KEY-super-secret-value-123"


@pytest.fixture
def keys(monkeypatch):
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setenv("TELNYX_PUBLIC_KEY", base64.b64encode(raw).decode())
    return private


@pytest.fixture
def calls():
    return []


@pytest.fixture
def client(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            {"url": str(request.url), "auth": request.headers.get("authorization"), "body": json.loads(request.content or b"{}")}
        )
        return httpx.Response(200, json={"data": {"result": "ok", "secret_echo": SECRET_API_KEY}})

    application = create_app("sqlite://")
    application.state.telnyx_transport = httpx.MockTransport(handler)
    with TestClient(application) as test_client:
        yield test_client


def event(event_id="evt-1", event_type="call.initiated", control_id="v3:abc-123", frm="+84901234567", to="+842873001234"):
    return {
        "data": {
            "id": event_id,
            "event_type": event_type,
            "payload": {"call_control_id": control_id, "from": frm, "to": to},
        }
    }


def signed(private, payload, timestamp=None, tamper=False):
    body = json.dumps(payload).encode()
    stamp = str(int(time.time()) if timestamp is None else timestamp)
    signature = private.sign(stamp.encode() + b"|" + body)
    if tamper:
        signature = bytes([signature[0] ^ 1]) + signature[1:]
    headers = {
        "telnyx-signature-ed25519": base64.b64encode(signature).decode(),
        "telnyx-timestamp": stamp,
        "content-type": "application/json",
    }
    return body, headers


def post(client, private, payload, **kwargs):
    body, headers = signed(private, payload, **kwargs)
    return client.post("/telnyx/webhook", content=body, headers=headers)


def test_unconfigured_webhook_is_503(client):
    r = client.post("/telnyx/webhook", json=event())
    assert r.status_code == 503


def test_invalid_public_key_counts_as_unconfigured(client, monkeypatch):
    monkeypatch.setenv("TELNYX_PUBLIC_KEY", "not base64 !!")
    assert client.post("/telnyx/webhook", json=event()).status_code == 503
    monkeypatch.setenv("TELNYX_PUBLIC_KEY", base64.b64encode(b"short").decode())
    assert client.post("/telnyx/webhook", json=event()).status_code == 503


def test_webhook_is_public_but_needs_a_signature(client, keys):
    assert client.post("/telnyx/webhook", json=event()).status_code == 401
    body, headers = signed(keys, event())
    assert client.post("/telnyx/webhook", content=body, headers={"telnyx-signature-ed25519": headers["telnyx-signature-ed25519"]}).status_code == 401
    assert client.post("/telnyx/webhook", content=body, headers={"telnyx-timestamp": headers["telnyx-timestamp"]}).status_code == 401


def test_valid_signature_is_accepted_without_cookie_and_ignores_origin(client, keys):
    body, headers = signed(keys, event())
    r = client.post("/telnyx/webhook", content=body, headers={**headers, "Origin": "https://api.telnyx.com"})
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_bad_signatures_are_401(client, keys):
    assert post(client, keys, event(), tamper=True).status_code == 401
    other = Ed25519PrivateKey.generate()
    assert post(client, other, event()).status_code == 401
    body, headers = signed(keys, event())
    assert client.post("/telnyx/webhook", content=body + b" ", headers=headers).status_code == 401  # body changed
    for bad in ("", "!!!", "QUJD"):
        assert client.post("/telnyx/webhook", content=body, headers={**headers, "telnyx-signature-ed25519": bad}).status_code == 401


def test_old_future_and_malformed_timestamps_are_401(client, keys):
    assert post(client, keys, event(), timestamp=int(time.time()) - 301).status_code == 401
    assert post(client, keys, event(), timestamp=int(time.time()) + 301).status_code == 401
    assert post(client, keys, event(), timestamp=int(time.time()) - 200).status_code == 200
    body, headers = signed(keys, event())
    for bad in ("abc", "-5", "1.5", ""):
        assert client.post("/telnyx/webhook", content=body, headers={**headers, "telnyx-timestamp": bad}).status_code == 401


def test_timestamp_is_part_of_the_signed_payload(client, keys):
    body, headers = signed(keys, event(), timestamp=int(time.time()))
    shifted = {**headers, "telnyx-timestamp": str(int(headers["telnyx-timestamp"]) + 1)}
    assert client.post("/telnyx/webhook", content=body, headers=shifted).status_code == 401


def test_oversize_body_is_413(client, keys):
    big = {"data": {"id": "x", "event_type": "call.initiated", "pad": "a" * telnyx.MAX_BODY_BYTES}}
    assert post(client, keys, big).status_code == 413
    body, headers = signed(keys, event())
    declared = client.post("/telnyx/webhook", content=body, headers={**headers, "content-length": str(telnyx.MAX_BODY_BYTES + 1)})
    assert declared.status_code in (400, 413)


def test_malformed_events_after_a_valid_signature(client, keys):
    for payload in ({}, {"data": {}}, {"data": {"id": "x"}}, {"data": {"event_type": "call.answered"}}, {"data": 5}, [1], {"data": {"id": 5, "event_type": "x"}}, {"data": {"id": "", "event_type": "call.initiated"}}, {"data": {"id": "x" * 101, "event_type": "call.initiated"}}):
        assert post(client, keys, payload).status_code == 400
    body = b"not json"
    stamp = str(int(time.time()))
    sig = base64.b64encode(keys.sign(stamp.encode() + b"|" + body)).decode()
    r = client.post("/telnyx/webhook", content=body, headers={"telnyx-signature-ed25519": sig, "telnyx-timestamp": stamp})
    assert r.status_code == 400


def test_initiated_answers_the_call(client, keys, calls, monkeypatch):
    monkeypatch.setenv("TELNYX_API_KEY", SECRET_API_KEY)
    assert post(client, keys, event()).status_code == 200
    assert len(calls) == 1
    assert calls[0]["url"] == "https://api.telnyx.com/v2/calls/v3%3Aabc-123/actions/answer"
    assert calls[0]["auth"] == f"Bearer {SECRET_API_KEY}"


def test_answered_speaks_then_records(client, keys, calls, monkeypatch):
    monkeypatch.setenv("TELNYX_API_KEY", SECRET_API_KEY)
    monkeypatch.setenv("TELNYX_GREETING", "Chào bạn")
    assert post(client, keys, event("e2", "call.answered")).status_code == 200
    assert [c["url"].rsplit("/", 1)[1] for c in calls] == ["speak", "record_start"]
    assert calls[0]["body"]["payload"] == "Chào bạn"
    assert calls[1]["body"]["format"] == "mp3"


def test_default_greeting_is_vietnamese_and_capped(client, keys, calls, monkeypatch):
    monkeypatch.setenv("TELNYX_API_KEY", SECRET_API_KEY)
    post(client, keys, event("e3", "call.answered"))
    assert calls[0]["body"]["payload"] == telnyx.DEFAULT_GREETING
    calls.clear()
    monkeypatch.setenv("TELNYX_GREETING", "x" * 900)
    post(client, keys, event("e4", "call.answered"))
    assert len(calls[0]["body"]["payload"]) == telnyx.MAX_GREETING_CHARS


def test_recording_saved_only_stores_metadata(client, keys, calls, monkeypatch, admin):
    monkeypatch.setenv("TELNYX_API_KEY", SECRET_API_KEY)
    payload = event("e5", "call.recording.saved")
    payload["data"]["payload"]["recording_urls"] = {"mp3": "https://example.test/rec.mp3"}
    assert post(client, keys, payload).status_code == 200
    assert calls == []  # no API call, no download
    rows = client.get("/calls", headers=admin).json()
    assert rows[0]["eventType"] == "call.recording.saved"
    assert "example.test" not in json.dumps(rows)


def test_without_api_key_events_are_stored_but_no_api_calls(client, keys, calls, admin):
    assert post(client, keys, event()).status_code == 200
    assert calls == []
    assert len(client.get("/calls", headers=admin).json()) == 1


def test_unhandled_event_types_are_acknowledged_and_not_stored(client, keys, calls, monkeypatch, admin):
    monkeypatch.setenv("TELNYX_API_KEY", SECRET_API_KEY)
    r = post(client, keys, event("e6", "call.hangup"))
    assert r.status_code == 200 and r.json() == {"status": "ignored"}
    assert calls == [] and client.get("/calls", headers=admin).json() == []


def test_idempotent_on_the_event_id(client, keys, calls, monkeypatch, admin):
    monkeypatch.setenv("TELNYX_API_KEY", SECRET_API_KEY)
    assert post(client, keys, event("same")).json() == {"status": "ok"}
    assert post(client, keys, event("same")).json() == {"status": "duplicate"}
    assert len(calls) == 1  # the call is answered once
    assert len(client.get("/calls", headers=admin).json()) == 1


def test_race_on_the_unique_key_is_a_duplicate(client, keys, monkeypatch, admin):
    original = telnyx.select

    class Hide:
        """Pretend the pre-check found nothing so the unique constraint is what stops the second insert."""

    post(client, keys, event("race"))
    monkeypatch.setattr(telnyx.Session, "scalar", lambda self, *a, **k: None, raising=False)
    assert post(client, keys, event("race")).json() == {"status": "duplicate"}
    assert len(client.get("/calls", headers=admin).json()) == 1
    assert original is telnyx.select


def test_numbers_are_masked_and_nothing_else_is_kept(client, keys, admin):
    post(client, keys, event("m1", frm="+84 (901) 234-567", to="+842873001234"))
    row = client.get("/calls", headers=admin).json()[0]
    assert row["from"] == "*********67" and row["to"] == "**********34"
    dumped = json.dumps(row)
    assert "0123" not in dumped and "84901" not in dumped and "2873" not in dumped
    assert row["payloadSize"] > 0 and row["callControlId"] == "v3:abc-123"
    assert set(row) == {"id", "eventType", "callControlId", "from", "to", "payloadSize", "createdAt"}


@pytest.mark.parametrize(
    "value,expected",
    [("+84901234567", "*********67"), ("12", "12"[:0] + "**"), ("1", "*"), (None, ""), (5, ""), ("abc", ""), ("123", "*23"), ("9" * 40, "*" * 18 + "99")],
)
def test_mask_number(value, expected):
    assert telnyx.mask_number(value) == expected


def test_missing_number_fields_store_empty_strings(client, keys, admin):
    payload = {"data": {"id": "n1", "event_type": "call.initiated", "payload": {"call_control_id": "id1"}}}
    assert post(client, keys, payload).status_code == 200
    row = client.get("/calls", headers=admin).json()[0]
    assert row["from"] == "" and row["to"] == ""
    odd = {"data": {"id": "n2", "event_type": "call.initiated", "payload": "nope"}}
    assert post(client, keys, odd).status_code == 200


def test_suspicious_call_control_id_is_stored_but_never_used_in_a_url(client, keys, calls, monkeypatch):
    monkeypatch.setenv("TELNYX_API_KEY", SECRET_API_KEY)
    assert post(client, keys, event("bad1", control_id="../../x?y=1#z")).status_code == 200
    assert post(client, keys, event("bad2", control_id="")).status_code == 200
    assert calls == []


def test_api_key_and_responses_are_never_logged(client, keys, caplog, monkeypatch):
    monkeypatch.setenv("TELNYX_API_KEY", SECRET_API_KEY)
    with caplog.at_level(logging.DEBUG):
        post(client, keys, event("l1"))
        post(client, keys, event("l2", "call.answered"))
    assert SECRET_API_KEY not in caplog.text
    assert "secret_echo" not in caplog.text


def test_api_failures_do_not_fail_the_webhook_nor_leak(keys, caplog, monkeypatch):
    monkeypatch.setenv("TELNYX_API_KEY", SECRET_API_KEY)

    def fail(request):
        raise httpx.ConnectTimeout("timed out while talking to " + SECRET_API_KEY)

    application = create_app("sqlite://")
    application.state.telnyx_transport = httpx.MockTransport(fail)
    with TestClient(application) as client, caplog.at_level(logging.DEBUG):
        assert post(client, keys, event("f1")).status_code == 200
    assert SECRET_API_KEY not in caplog.text
    assert "ConnectTimeout" in caplog.text


def test_api_error_status_is_logged_without_body(keys, caplog, monkeypatch):
    monkeypatch.setenv("TELNYX_API_KEY", SECRET_API_KEY)
    application = create_app("sqlite://")
    application.state.telnyx_transport = httpx.MockTransport(lambda r: httpx.Response(401, text="bad key " + SECRET_API_KEY))
    with TestClient(application) as client, caplog.at_level(logging.DEBUG):
        assert post(client, keys, event("f2")).status_code == 200
    assert "HTTP 401" in caplog.text and SECRET_API_KEY not in caplog.text


def test_timeout_is_five_seconds():
    assert telnyx.API_TIMEOUT_SECONDS == 5.0 and telnyx.API_BASE == "https://api.telnyx.com/v2/calls"


def test_calls_listing_is_admin_only(client, keys, admin, alice):
    post(client, keys, event("a1"))
    post(client, keys, event("a2", "call.answered"))
    post(client, keys, event("a3", "call.recording.saved"))
    assert client.get("/calls").status_code == 401
    assert client.get("/calls", headers=alice).status_code == 403
    assert client.get("/calls", headers=auth_cookie(9, "x", role="moderator")).status_code == 403
    rows = client.get("/calls", headers=admin).json()
    assert [r["eventType"] for r in rows] == ["call.recording.saved", "call.answered", "call.initiated"]  # newest first
    assert len(client.get("/calls", params={"limit": 2}, headers=admin).json()) == 2
    for bad in (0, 201, "x"):
        assert client.get("/calls", params={"limit": bad}, headers=admin).status_code == 422


def test_old_events_are_trimmed(client, keys, monkeypatch, admin):
    monkeypatch.setattr(telnyx, "MAX_STORED_EVENTS", 2)
    for index in range(4):
        post(client, keys, event(f"t{index}"))
    assert len(client.get("/calls", headers=admin).json()) == 2
