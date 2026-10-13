"""QR sign-in: a new device asks, a signed-in device approves."""

import threading
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app import qr
from app.models import QrLogin, UserSession, utcnow
from tests.helpers import csrf, register
from tests.mail_helpers import EMAIL, sent_to, set_user, verified_account

UA = {"user-agent": "NewBrowser/1.0"}


def new_device(client) -> TestClient:
    return TestClient(client.app)  # its own cookie jar


def start(device):
    response = device.post("/auth/qr/start", headers=UA)
    assert response.status_code == 201, response.text
    return response.json()


def poll(device, started, token=None):
    return device.post(
        "/auth/qr/poll", json={"request_id": started["request_id"], "poll_token": token or started["poll_token"]}
    )


def approve(client, session, started, code=None):
    return client.post(
        f"/auth/qr/{started['request_id']}/approve",
        json={"verify_code": code or started["verify_code"]}, headers=csrf(session),
    )


def row(client, request_id) -> QrLogin:
    with client.app.state.session_factory() as db:
        return db.get(QrLogin, request_id)


def edit(client, request_id, **values):
    with client.app.state.session_factory() as db:
        db.execute(update(QrLogin).where(QrLogin.id == request_id).values(**values))
        db.commit()


def test_start_shape_and_fragment_only_secret(client):
    started = start(new_device(client))
    assert set(started) == {"request_id", "poll_token", "verify_code", "expires_in", "qr_url"}
    assert started["expires_in"] == 120 and len(started["request_id"]) == 32
    assert len(started["verify_code"]) == 4 and set(started["verify_code"]) <= set(qr.CODE_ALPHABET)
    url = started["qr_url"]
    assert url == f"http://localhost:8080/login/qr#r={started['request_id']}"
    assert started["poll_token"] not in url and "?" not in url
    stored = row(client, started["request_id"])
    assert stored.poll_hash != started["poll_token"] and started["poll_token"] not in stored.poll_hash
    assert stored.requester_user_agent == "NewBrowser/1.0" and stored.status == "pending"


def test_happy_path_logs_the_new_device_in_once(client):
    session = register(client)
    device = new_device(client)
    started = start(device)
    assert poll(device, started).json() == {"status": "pending"}
    info = client.get(f"/auth/qr/{started['request_id']}")
    assert info.status_code == 200
    body = info.json()
    assert set(body) == {"requester_ip", "requester_user_agent", "created_at", "expires_in"}
    assert started["verify_code"] not in info.text and body["requester_user_agent"] == "NewBrowser/1.0"
    assert approve(client, session, started).json() == {"status": "approved"}
    done = poll(device, started)
    assert done.status_code == 200 and set(done.json()) == {"id", "username", "role", "csrf_token"}
    assert device.get("/auth/me").json()["username"] == "alice"
    with client.app.state.session_factory() as db:
        methods = [r.method for r in db.scalars(select(UserSession))]
    assert sorted(methods) == ["password", "qr"]
    assert client.get("/auth/me").status_code == 200  # approving revokes nothing
    assert row(client, started["request_id"]).status == "consumed"


def test_replay_after_consume_is_refused(client):
    session = register(client)
    device = new_device(client)
    started = start(device)
    approve(client, session, started)
    assert poll(device, started).status_code == 200
    again = poll(new_device(client), started)
    assert again.status_code == 404 and "set-cookie" not in again.headers


def test_parallel_polls_issue_exactly_one_session(mail_file_client):
    client = mail_file_client
    session = register(client)
    started = start(new_device(client))
    approve(client, session, started)
    results = []

    def go():
        results.append(poll(new_device(client), started).status_code)

    threads = [threading.Thread(target=go) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [200, 404, 404, 404]


def test_consume_is_conditional(client):
    session = register(client)
    started = start(new_device(client))
    approve(client, session, started)
    with client.app.state.session_factory() as a, client.app.state.session_factory() as b:
        assert qr.consume(a, started["request_id"]) is True
        assert qr.consume(b, started["request_id"]) is False


def test_wrong_poll_token_and_unknown_id_look_alike(client):
    device = new_device(client)
    started = start(device)
    wrong = poll(device, started, token="x" * 43)
    unknown = device.post("/auth/qr/poll", json={"request_id": "0" * 32, "poll_token": "x" * 43})
    assert wrong.status_code == unknown.status_code == 404 and wrong.json() == unknown.json()
    assert poll(device, started).json() == {"status": "pending"}  # the real request is untouched


def test_wrong_code_counts_and_three_deny(client):
    session = register(client)
    device = new_device(client)
    started = start(device)
    wrong = "AAAA" if started["verify_code"] != "AAAA" else "BBBB"
    assert approve(client, session, started, wrong).status_code == 403
    assert approve(client, session, started, wrong).status_code == 403
    assert row(client, started["request_id"]).status == "pending"
    assert approve(client, session, started, wrong).status_code == 403
    assert row(client, started["request_id"]).status == "denied"
    assert approve(client, session, started).status_code == 404  # even the right code is too late now
    assert poll(device, started).json() == {"status": "denied"}


def test_code_is_case_insensitive(client):
    session = register(client)
    started = start(new_device(client))
    assert approve(client, session, started, started["verify_code"].lower()).status_code == 200


def test_deny(client):
    session = register(client)
    device = new_device(client)
    started = start(device)
    assert client.post(f"/auth/qr/{started['request_id']}/deny", headers=csrf(session)).json() == {"status": "denied"}
    assert poll(device, started).json() == {"status": "denied"}
    assert client.post(f"/auth/qr/{started['request_id']}/deny", headers=csrf(session)).status_code == 404
    assert "sn_token" not in device.cookies


def test_expiry(client):
    session = register(client)
    device = new_device(client)
    started = start(device)
    edit(client, started["request_id"], expires_at=utcnow() - timedelta(seconds=1))
    assert poll(device, started).json() == {"status": "expired"}
    assert client.get(f"/auth/qr/{started['request_id']}").status_code == 404
    assert approve(client, session, started).status_code == 404


def test_approved_but_expired_is_not_consumed(client):
    session = register(client)
    device = new_device(client)
    started = start(device)
    approve(client, session, started)
    edit(client, started["request_id"], expires_at=utcnow() - timedelta(seconds=1))
    assert poll(device, started).json() == {"status": "expired"}
    assert row(client, started["request_id"]).status == "approved"


def test_phone_side_needs_a_session_and_csrf(client):
    session = register(client)
    started = start(new_device(client))
    path = f"/auth/qr/{started['request_id']}"
    anonymous = new_device(client)
    assert anonymous.get(path).status_code == 401
    assert anonymous.post(f"{path}/approve", json={"verify_code": started["verify_code"]}).status_code == 401
    assert client.post(f"{path}/approve", json={"verify_code": started["verify_code"]}).status_code == 403
    assert client.post(f"{path}/deny").status_code == 403
    assert client.get("/auth/qr/" + "f" * 32).status_code == 404
    assert approve(client, session, started).status_code == 200


def test_the_requesting_browser_cannot_approve_itself(client):
    session = register(client)
    started = start(client)  # same cookie jar: the requester is already signed in
    assert approve(client, session, started).status_code == 403
    assert row(client, started["request_id"]).status == "pending"


def test_account_with_totp_gets_mfa_required(client):
    session = register(client)
    set_user(client, totp_enabled=True)
    device = new_device(client)
    started = start(device)
    approve(client, session, started)
    body = poll(device, started).json()
    assert body["mfa_required"] is True and body["factors"] == ["totp"] and "sn_token" not in device.cookies


def test_origin_is_checked(client):
    response = client.post("/auth/qr/start", headers={"origin": "https://evil.example"})
    assert response.status_code == 403


def test_start_and_poll_are_throttled_per_ip(client):
    device = new_device(client)
    started = start(device)
    for _ in range(9):
        assert device.post("/auth/qr/start").status_code == 201
    assert device.post("/auth/qr/start").status_code == 429
    for _ in range(200):
        assert poll(device, started).status_code == 200
    assert poll(device, started).status_code == 429


def test_approval_sends_a_security_notice(mail_client):
    client = mail_client
    session = verified_account(client)
    started = start(new_device(client))
    approve(client, session, started)
    mails = sent_to(client, EMAIL)
    assert len(mails) == 1 and "mã QR" in mails[0].subject
    assert "NewBrowser/1.0" in mails[0].text and "testclient" in mails[0].text


def test_no_mail_without_a_verified_email(mail_client):
    session = register(mail_client)
    started = start(new_device(mail_client))
    approve(mail_client, session, started)
    assert mail_client.app.state.mailer.sent == []


def test_old_rows_are_purged_on_start(client):
    old = start(new_device(client))
    edit(client, old["request_id"], expires_at=utcnow() - timedelta(hours=2))
    recent = start(new_device(client))
    assert row(client, old["request_id"]) is None and row(client, recent["request_id"]) is not None


def test_user_agent_is_truncated(client):
    device = new_device(client)
    started = device.post("/auth/qr/start", headers={"user-agent": "x" * 500}).json()
    assert len(row(client, started["request_id"]).requester_user_agent) == 200


def test_attempts_are_spent_before_comparing(client):
    session = register(client)
    started = start(new_device(client))
    rid = started["request_id"]
    with client.app.state.session_factory() as db:
        assert [qr.take_attempt(db, rid) for _ in range(5)] == [True, True, True, False, False]
    assert approve(client, session, started).status_code == 404  # tries exhausted: even the right code is refused


def test_poll_and_approve_purge_old_rows(client, monkeypatch):
    session = register(client)
    old = start(new_device(client))
    edit(client, old["request_id"], expires_at=utcnow() - timedelta(hours=2))
    live = start(new_device(client))
    monkeypatch.setattr(qr, "_last_purge", 0.0)
    assert poll(new_device(client), live).status_code == 200
    assert row(client, old["request_id"]) is None
    old2 = start(new_device(client))
    edit(client, old2["request_id"], expires_at=utcnow() - timedelta(hours=2))
    monkeypatch.setattr(qr, "_last_purge", 0.0)
    approve(client, session, live)
    assert row(client, old2["request_id"]) is None
