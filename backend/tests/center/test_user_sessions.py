"""Device list, per-session revocation (here and in every other app), and the sid claim."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from api.center import cli, usersessions
from api.center.models import User, UserSession, utcnow
from api.center.tokens import create_refresh_token, csrf_token, decode_claims
from sn_shared import COOKIE_NAME, AuthError, create_token, decode_token, revocation
from sn_shared.security import payload_from_cookies
from tests.center.helpers import CREDS, STRONG, cookie_value, csrf, refresh_with, register, set_cookies
from tests.center.mail_helpers import PW, code_of, last_mail, set_user
from tests.center.test_passkeys import passkey_only
from tests.center.test_totp import clock, code_at, second_step, turn_on  # noqa: F401 - clock is a fixture

KEEP = {"detail": "Keep at least one sign-in method"}


def rows(client) -> list[UserSession]:
    with client.app.state.session_factory() as db:
        return list(db.scalars(select(UserSession).order_by(UserSession.created_at, UserSession.sid)))


def second_device(client) -> TestClient:
    """Another browser (own cookie jar) on the same app, signed in as Alice."""
    other = TestClient(client.app)
    assert other.post("/auth/login", json=CREDS).status_code == 200
    return other


def listed(client) -> list[dict]:
    response = client.get("/auth/sessions")
    assert response.status_code == 200, response.text
    return response.json()


def current_sid(client) -> str:
    return decode_token(client.cookies.get(COOKIE_NAME)).sid


# --- the sid claim and the row ---------------------------------------------------------------------------


def test_sign_in_creates_a_row_and_puts_the_sid_in_both_tokens(client):
    response = client.post("/auth/register", json=CREDS, headers={"user-agent": "UA/" + "x" * 300})
    (row,) = rows(client)
    access, refresh = cookie_value(response, "sn_token"), cookie_value(response, "sn_refresh")
    assert len(row.sid) == 32 and int(row.sid, 16) >= 0
    assert decode_token(access).sid == row.sid
    assert decode_claims(refresh, "refresh")["sid"] == row.sid
    assert (row.method, row.ip, row.revoked_at) == ("password", "testclient", None)
    assert row.user_agent == ("UA/" + "x" * 300)[:200]


def test_refresh_keeps_the_sid_and_adds_no_row(client):
    response = client.post("/auth/register", json=CREDS)
    refresh = cookie_value(response, "sn_refresh")
    sid = rows(client)[0].sid

    again = refresh_with(client, refresh)

    assert again.status_code == 200
    assert decode_token(cookie_value(again, "sn_token")).sid == sid
    assert decode_claims(cookie_value(again, "sn_refresh"), "refresh")["sid"] == sid
    assert len(rows(client)) == 1


def test_a_token_whose_row_is_missing_is_rejected_everywhere_in_center(client):
    response = client.post("/auth/register", json=CREDS)
    refresh = cookie_value(response, "sn_refresh")
    with client.app.state.session_factory() as db:
        db.query(UserSession).delete()
        db.commit()
    assert client.get("/auth/me").status_code == 401
    assert refresh_with(client, refresh).status_code == 401


def test_tokens_without_a_sid_still_work_as_access_tokens_but_never_refresh(client):
    session = register(client)
    with client.app.state.session_factory() as db:
        db.query(UserSession).delete()
        db.commit()
    client.cookies.set(COOKIE_NAME, create_token(session["id"], "alice", ver=0), path="/")  # no sid
    assert client.get("/auth/me").status_code == 200
    assert client.get("/auth/sessions").json() == []  # nothing to list: it has no row

    again = refresh_with(client, create_refresh_token(session["id"], 0, 600))  # no sid

    assert again.status_code == 401 and rows(client) == []  # generic 401, no row created


def test_first_start_with_sessions_forces_one_relogin(tmp_path):
    from api.center.main import create_app
    from tests.center.test_migrate import make_old_db

    url = make_old_db(tmp_path / "old.db")
    with TestClient(create_app(url)) as first:
        with first.app.state.session_factory() as db:
            assert db.scalar(select(User.token_version)) == 1
    with TestClient(create_app(url)) as second:  # not again on the next start
        with second.app.state.session_factory() as db:
            assert db.scalar(select(User.token_version)) == 1


def test_a_fresh_database_is_not_bumped(client):
    register(client)
    assert client.app.state.session_factory
    with client.app.state.session_factory() as db:
        assert db.scalar(select(User.token_version)) == 0


def test_cli_on_an_old_database_forces_the_relogin_too(tmp_path, monkeypatch):
    from tests.center.test_migrate import make_old_db

    monkeypatch.setenv("DATABASE_URL", make_old_db(tmp_path / "old.db"))
    with cli.open_session_cli() as db:
        assert db.scalar(select(User.token_version)) == 1


def test_beyond_fifty_live_sessions_the_oldest_are_revoked(client, revocations):
    register(client)
    with client.app.state.session_factory() as db:
        for i in range(usersessions.MAX_LIVE_SESSIONS):
            db.add(UserSession(sid=f"{i:032x}", user_id=1, created_at=utcnow() - timedelta(days=2, minutes=-i),
                               last_seen_at=utcnow(), method="password"))  # fmt: skip
        db.commit()
    assert client.post("/auth/login", json=CREDS).status_code == 200
    with client.app.state.session_factory() as db:
        live = usersessions.active_sessions(db, 1)
    assert len(live) == usersessions.MAX_LIVE_SESSIONS
    assert revocations.exists(f"sn:revoked:sid:{'0' * 32}") == 1  # the oldest one went, and was published


def test_old_revoked_rows_are_purged(client):
    register(client)
    with client.app.state.session_factory() as db:
        db.add(UserSession(sid="c" * 32, user_id=1, last_seen_at=utcnow(), method="password",
                           revoked_at=utcnow() - timedelta(days=2)))  # fmt: skip
        db.add(UserSession(sid="d" * 32, user_id=1, last_seen_at=utcnow(), method="password", revoked_at=utcnow()))
        db.commit()
    client.post("/auth/login", json=CREDS)
    sids = {r.sid for r in rows(client)}
    assert "c" * 32 not in sids and "d" * 32 in sids


def test_a_failed_publish_is_logged_as_a_warning_without_secrets(client, caplog):
    class Broken:
        def get(self, *a, **k):
            raise ConnectionError

        set = mget = get

    session = register(client)
    other = second_device(client)
    revocation.use_client(Broken())
    with caplog.at_level("WARNING", logger="auth.audit"):
        assert client.delete(f"/auth/sessions/{current_sid(other)}", headers=csrf(session)).status_code == 204
        client.post("/auth/me/password", json={"current_password": CREDS["password"], "new_password": STRONG},
                    headers=csrf(session))  # fmt: skip
    text = " | ".join(r.getMessage() for r in caplog.records)
    assert "revocation not published for 1 of 1 sessions" in text
    assert "minimum token version not published" in text
    assert current_sid(other) not in text


def test_last_seen_is_updated_at_most_once_a_minute(client):
    register(client)
    sid = rows(client)[0].sid
    old = utcnow() - timedelta(minutes=5)
    with client.app.state.session_factory() as db:
        db.execute(update(UserSession).values(last_seen_at=old))
        db.commit()

    assert client.get("/auth/me").status_code == 200
    first = rows(client)[0].last_seen_at
    assert usersessions.as_utc(first) > old + timedelta(minutes=4)

    assert client.get("/auth/me").status_code == 200
    assert rows(client)[0].last_seen_at == first  # inside the minute: no write
    assert rows(client)[0].sid == sid


def test_stale_rows_are_purged_on_the_next_sign_in(client):
    register(client)
    with client.app.state.session_factory() as db:
        db.add(UserSession(sid="a" * 32, user_id=1, last_seen_at=utcnow() - timedelta(days=30), method="password"))
        db.add(UserSession(sid="b" * 32, user_id=1, last_seen_at=utcnow() - timedelta(days=1), method="password"))
        db.commit()
    client.post("/auth/login", json=CREDS)
    assert {r.sid[0] for r in rows(client)} - {"a"} >= {"b"} and "a" * 32 not in {r.sid for r in rows(client)}


def test_deleting_the_account_deletes_its_rows(client):
    session = register(client)
    assert client.request("DELETE", "/auth/me", json=PW, headers=csrf(session)).status_code == 204
    assert rows(client) == []


# --- the primary factor is recorded -----------------------------------------------------------------------


def test_the_method_is_the_primary_factor_used(google_client):
    client = google_client
    client.post("/auth/google", json={"id_token": "sub-1|jane@example.com"})
    assert [r.method for r in rows(client)] == ["google"]
    client.cookies.clear()
    session, auth, _ = passkey_only(client)
    assert rows(client)[-1].method == "passkey"
    del session, auth


def test_email_code_login_is_recorded_as_email(mail_client):
    session = register(mail_client)
    set_user(mail_client, email="alice@example.com", email_verified=True)
    mail_client.cookies.clear()
    assert mail_client.post("/auth/email/login/request", json={"email": "alice@example.com"}).status_code == 202
    code = code_of(last_mail(mail_client, "alice@example.com"))
    done = mail_client.post("/auth/email/login/verify", json={"email": "alice@example.com", "code": code})
    assert done.status_code == 200 and session["id"] == done.json()["id"]
    assert rows(mail_client)[-1].method == "email"


def test_voice_and_webcam_sign_ups_are_recorded(bio_client):
    voice = bio_client.post(
        "/auth/register/voice", data={"username": "vera"}, files={"audio": ("v.webm", b"vera-voice-sample")}
    )
    bio_client.cookies.clear()
    cam = bio_client.post(
        "/auth/register/webcam", data={"username": "cam"}, files={"video": ("c.webm", b"vera-camera-clip")}
    )
    assert voice.status_code == cam.status_code == 201
    assert [r.method for r in rows(bio_client)] == ["voice", "webcam"]


def test_the_primary_factor_survives_the_second_step(client, clock):  # noqa: F811
    session = register(client)
    secret, _ = turn_on(client, session, clock)
    client.cookies.clear()
    clock.advance()
    assert second_step(client, code=code_at(secret, clock)).status_code == 200
    assert rows(client)[-1].method == "password"


def test_google_with_totp_is_recorded_as_google(google_client, clock):  # noqa: F811
    from tests.center.helpers import grant_fresh

    client = google_client
    session = client.post("/auth/google", json={"id_token": "sub-1|jane@example.com"}).json()
    grant_fresh(client)
    secret, _ = turn_on(client, session, clock)
    client.cookies.clear()
    body = client.post("/auth/google", json={"id_token": "sub-1|jane@example.com"}).json()
    clock.advance()
    done = client.post("/auth/login/totp", json={"mfa_token": body["mfa_token"], "code": code_at(secret, clock)})
    assert done.status_code == 200
    assert rows(client)[-1].method == "google"


# --- listing ----------------------------------------------------------------------------------------------


def test_list_is_newest_first_with_the_current_flag_and_exact_shape(client):
    register(client)
    other = second_device(client)
    other.headers["user-agent"] = "Other/1.0"

    items = listed(other)

    assert len(items) == 2 and items[0]["current"] is True and items[1]["current"] is False
    assert set(items[0]) == {"id", "current", "created_at", "last_seen_at", "ip", "user_agent", "method"}
    assert items[0]["id"] == current_sid(other) and items[0]["method"] == "password" and items[0]["ip"] == "testclient"
    assert items[0]["created_at"] >= items[1]["created_at"]
    assert items[0]["created_at"].endswith(("Z", "+00:00"))


def test_list_needs_login_and_hides_revoked_and_foreign_sessions(client):
    assert client.get("/auth/sessions").status_code == 401
    session = register(client)
    other = second_device(client)
    assert client.delete(f"/auth/sessions/{current_sid(other)}", headers=csrf(session)).status_code == 204
    TestClient(client.app).post("/auth/register", json={"username": "bob", "password": STRONG})
    assert [i["id"] for i in listed(client)] == [current_sid(client)]


# --- revoking ---------------------------------------------------------------------------------------------


def test_revoking_another_device_kills_it_here_and_in_the_other_apps(client, revocations):
    session = register(client)
    other = second_device(client)
    victim = current_sid(other)
    victim_access = other.cookies.get(COOKIE_NAME)
    assert other.get("/auth/me").status_code == 200

    response = client.delete(f"/auth/sessions/{victim}", headers=csrf(session))

    assert response.status_code == 204 and response.content == b""
    assert other.get("/auth/me").status_code == 401  # center checks the row
    assert client.get("/auth/me").status_code == 200  # the revoker is untouched
    assert revocations.exists(f"sn:revoked:sid:{victim}") == 1  # the other apps see it at once
    with pytest.raises(AuthError):
        payload_from_cookies({COOKIE_NAME: victim_access})
    ttl = revocations.ttl(f"sn:revoked:sid:{victim}")
    assert client.app.state.settings.access_minutes * 60 < ttl <= client.app.state.settings.access_minutes * 60 + 60


def test_a_revoked_device_cannot_refresh(client):
    session = register(client)
    other = second_device(client)
    refresh = other.cookies.get("sn_refresh", path="/api/center/auth")
    client.delete(f"/auth/sessions/{current_sid(other)}", headers=csrf(session))
    assert refresh_with(other, refresh).status_code == 401


def test_revoking_the_current_session_clears_the_cookies(client):
    session = register(client)
    response = client.delete(f"/auth/sessions/{current_sid(client)}", headers=csrf(session))
    assert response.status_code == 204
    cookies = set_cookies(response)
    assert all("Max-Age=0" in cookies[name] for name in ("sn_token", "sn_refresh", "sn_fresh"))
    assert client.get("/auth/me").status_code == 401


def test_only_own_live_sessions_can_be_revoked_and_every_miss_is_the_same_404(client):
    session = register(client)
    bob = TestClient(client.app)
    bob_session = bob.post("/auth/register", json={"username": "bob", "password": STRONG}).json()
    bob_sid = current_sid(bob)
    other = second_device(client)
    gone = current_sid(other)
    assert client.delete(f"/auth/sessions/{gone}", headers=csrf(session)).status_code == 204

    answers = [
        client.delete(f"/auth/sessions/{sid}", headers=csrf(session)).json()
        for sid in (bob_sid, "f" * 32, "nope", gone)  # foreign, unknown, malformed, already revoked
    ]
    assert answers == [{"detail": "Session not found"}] * 4
    assert bob.get("/auth/me", headers=csrf(bob_session)).status_code == 200


def test_revoke_others_counts_and_publishes_every_sid(client, revocations):
    session = register(client)
    first, second = second_device(client), second_device(client)
    sids = {current_sid(first), current_sid(second)}

    response = client.post("/auth/sessions/revoke-others", headers=csrf(session))

    assert response.status_code == 200 and response.json() == {"revoked": 2}
    assert {key.split(":")[-1] for key in revocations.scan_iter("sn:revoked:sid:*")} == sids
    assert first.get("/auth/me").status_code == second.get("/auth/me").status_code == 401
    assert client.get("/auth/me").status_code == 200
    assert client.post("/auth/sessions/revoke-others", headers=csrf(session)).json() == {"revoked": 0}


def test_session_writes_need_csrf_login_and_an_allowed_origin(client):
    session = register(client)
    sid = current_sid(client)
    assert client.delete(f"/auth/sessions/{sid}").status_code == 403
    assert client.post("/auth/sessions/revoke-others").status_code == 403
    bad = {**csrf(session), "Origin": "https://evil.example"}
    assert client.delete(f"/auth/sessions/{sid}", headers=bad).status_code == 403
    assert client.post("/auth/sessions/revoke-others", headers=bad).status_code == 403
    client.cookies.clear()
    assert client.delete(f"/auth/sessions/{sid}", headers=csrf(session)).status_code == 401
    assert client.post("/auth/sessions/revoke-others", headers=csrf(session)).status_code == 401


def test_revoking_works_without_a_redis(client):
    session = register(client)
    other = second_device(client)
    assert client.delete(f"/auth/sessions/{current_sid(other)}", headers=csrf(session)).status_code == 204
    assert other.get("/auth/me").status_code == 401


# --- token_version bumps also reach the other apps -----------------------------------------------------------


def user_version(client) -> int:
    with client.app.state.session_factory() as db:
        return db.scalar(select(User.token_version))


def test_logout_revokes_the_row_and_publishes_the_new_minimum_version(client, revocations):
    session = register(client)
    other = second_device(client)
    old_access = client.cookies.get(COOKIE_NAME)

    assert client.post("/auth/logout", headers=csrf(session)).status_code == 204

    assert all(r.revoked_at is not None for r in rows(client))
    assert other.get("/auth/me").status_code == 401  # logout ends every session of the account
    assert revocations.get("sn:minver:1") == str(user_version(client)) == "1"
    with pytest.raises(AuthError):
        payload_from_cookies({COOKIE_NAME: old_access})


def test_password_change_keeps_this_session_revokes_the_others_and_publishes(client, revocations):
    session = register(client)
    other = second_device(client)
    mine = current_sid(client)

    changed = client.post(
        "/auth/me/password", json={"current_password": CREDS["password"], "new_password": STRONG}, headers=csrf(session)
    )

    assert changed.status_code == 200
    assert current_sid(client) == mine  # same session, re-issued
    assert [i["id"] for i in listed(client)] == [mine]
    assert other.get("/auth/me").status_code == 401
    assert revocations.get("sn:minver:1") == "1"
    assert payload_from_cookies({COOKIE_NAME: client.cookies.get(COOKIE_NAME)}).ver == 1  # the new token passes


def test_a_legacy_session_that_changes_its_password_is_upgraded_to_a_row(client):
    session = register(client)
    with client.app.state.session_factory() as db:
        db.query(UserSession).delete()
        db.commit()
    legacy = create_token(session["id"], "alice", ver=0)
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, legacy, path="/")
    csrf_value = {"X-CSRF-Token": csrf_token(legacy)}
    changed = client.post(
        "/auth/me/password", json={"current_password": CREDS["password"], "new_password": STRONG}, headers=csrf_value
    )
    assert changed.status_code == 200
    (row,) = rows(client)
    assert row.method == "refresh" and decode_token(cookie_value(changed, "sn_token")).sid == row.sid


def test_totp_changes_publish_the_version_and_keep_the_session(client, revocations, clock):  # noqa: F811
    session = register(client)
    mine = current_sid(client)
    turn_on(client, session, clock)
    assert current_sid(client) == mine and revocations.get("sn:minver:1") == "1"


def test_password_reset_publishes_the_version(mail_client, revocations):
    from tests.center.mail_helpers import token_of

    register(mail_client)
    set_user(mail_client, email="alice@example.com", email_verified=True)
    mail_client.post("/auth/password/forgot", json={"email": "alice@example.com"})
    token = token_of(last_mail(mail_client, "alice@example.com"))
    done = mail_client.post("/auth/password/reset", json={"token": token, "new_password": STRONG})
    assert done.status_code == 200
    assert revocations.get("sn:minver:1") == "1"
    assert all(r.revoked_at is not None for r in rows(mail_client))


def test_the_admin_cli_publishes_the_version(client, revocations, monkeypatch):
    register(client)
    factory = client.app.state.session_factory
    monkeypatch.setenv("JWT_SECRET", "t" * 40)
    assert cli.main(["reset-password", "alice"], read_password=lambda: STRONG, open_session=factory) == 0
    assert revocations.get("sn:minver:1") == "1"
    assert cli.main(["demote", "alice"], open_session=factory) == 0
    assert revocations.get("sn:minver:1") == "2"
    monkeypatch.delenv("JWT_SECRET")  # unusable settings: a warning, not a crash
    assert cli.main(["demote", "alice"], open_session=factory) == 0


def test_a_broken_revocation_store_never_breaks_revoking(client):
    class Broken:
        def get(self, *a, **k):
            raise ConnectionError

        set = mget = get

    session = register(client)
    other = second_device(client)
    revocation.use_client(Broken())
    assert client.delete(f"/auth/sessions/{current_sid(other)}", headers=csrf(session)).status_code == 204
    assert other.get("/auth/me").status_code == 401  # center's own check is the database
    assert revocation.is_revoked(1, "s" * 32, 0) is False  # and the other apps fail open
