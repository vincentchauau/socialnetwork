"""Notifications, registration with an email, disabled email, configuration and the schema upgrade."""

import logging

import pytest
import sqlalchemy as sa

from api.center.config import ConfigError, Settings
from api.center.db import make_engine
from api.center.mailer import SmtpMailer
from api.center.main import create_app
from api.center.migrate import ensure_columns
from tests.center.helpers import CREDS, STRONG, csrf, register
from tests.center.mail_helpers import EMAIL, PW, code_of, last_mail, sent_to, set_user, token_of, token_rows, user_row, verified_account
from tests.center.test_migrate import make_old_db
from tests.center.test_passkeys import link as link_passkey

VOICE = ("v.webm", b"vera-voice-sample")
CAM = ("c.webm", b"vera-camera-clip")


# --- notifications -----------------------------------------------------------------------------


def only_mail(client):
    messages = client.app.state.mailer.sent
    assert len(messages) == 1, [m.subject for m in messages]
    message = messages[0]
    assert message.to == EMAIL and message.html
    messages.clear()
    return message


def test_every_security_event_notifies_a_verified_address(mail_bio_client):
    client = mail_bio_client
    session = verified_account(client)
    subjects = []

    changed = client.post(
        "/auth/me/password", json={"current_password": CREDS["password"], "new_password": STRONG}, headers=csrf(session)
    )
    assert changed.status_code == 200
    subjects.append(only_mail(client).subject)
    pw = {"password": STRONG}
    headers = csrf(changed.json())

    _, _, added = link_passkey(client, changed.json(), body=pw)
    assert added.status_code == 200
    subjects.append(only_mail(client).subject)
    passkey_id = added.json()["passkeys"][0]["id"]
    assert client.request("DELETE", f"/auth/me/passkeys/{passkey_id}", json=pw, headers=headers).status_code == 200
    subjects.append(only_mail(client).subject)

    assert client.post("/auth/me/voice", data=pw, files={"audio": VOICE}, headers=headers).status_code == 200
    subjects.append(only_mail(client).subject)
    assert client.request("DELETE", "/auth/me/voice", data=pw, headers=headers).status_code == 200
    subjects.append(only_mail(client).subject)
    assert client.post("/auth/me/webcam", data=pw, files={"video": CAM}, headers=headers).status_code == 200
    subjects.append(only_mail(client).subject)
    assert client.request("DELETE", "/auth/me/webcam", data=pw, headers=headers).status_code == 200
    subjects.append(only_mail(client).subject)

    linked = client.post("/auth/me/google", json={"id_token": "sub-1|other@example.com", **pw}, headers=headers)
    assert linked.status_code == 200
    subjects.append(only_mail(client).subject)
    assert client.request("DELETE", "/auth/me/google", json=pw, headers=headers).status_code == 200
    subjects.append(only_mail(client).subject)

    assert client.request("DELETE", "/auth/me/email", json=pw, headers=headers).status_code == 200
    subjects.append(only_mail(client).subject)
    set_user(client, email=EMAIL, email_verified=True)

    assert client.request("DELETE", "/auth/me", json=pw, headers=headers).status_code == 204
    subjects.append(only_mail(client).subject)

    assert len(set(subjects)) == len(subjects)  # one short template per event


def test_every_listed_event_has_a_template():
    from api.center.mailtemplates import EVENTS

    assert {
        "password_changed", "password_reset", "email_changed", "email_removed", "passkey_added", "passkey_removed",
        "google_linked", "google_unlinked", "voice_added", "voice_removed", "webcam_added", "webcam_removed",
        "account_deleted",
    } <= set(EVENTS)  # fmt: skip


def test_no_notification_for_an_unverified_address(mail_bio_client):
    client = mail_bio_client
    session = register(client)
    set_user(client, email=EMAIL, email_verified=False)
    client.post("/auth/me/password", json={"current_password": CREDS["password"], "new_password": STRONG}, headers=csrf(session))
    assert client.app.state.mailer.sent == []


def test_no_notification_without_an_address(mail_client):
    session = register(mail_client)
    mail_client.post("/auth/me/password", json={"current_password": CREDS["password"], "new_password": STRONG}, headers=csrf(session))
    assert mail_client.app.state.mailer.sent == []


def test_a_mail_failure_never_reaches_the_client_and_is_logged_by_type_only(mail_client, caplog):
    caplog.set_level(logging.INFO, logger="auth.audit")
    session = register(mail_client)
    mail_client.app.state.mailer.fail = True

    response = mail_client.post("/auth/me/email", json={"email": EMAIL, **PW}, headers=csrf(session))

    assert (response.status_code, response.json()) == (202, {"ok": True})
    assert "RuntimeError" in caplog.text and "smtp is down" not in caplog.text and EMAIL not in caplog.text


# --- registration with an email ----------------------------------------------------------------


def combined(client, **fields):
    return client.post("/auth/register/combined", data=fields)


def test_register_with_email_sends_a_verify_mail_and_the_account_starts_unverified(mail_client):
    response = combined(mail_client, username="carol", password="Carols-Pass-1", email=" Carol@Example.com ")

    assert response.status_code == 201
    mail = last_mail(mail_client, "carol@example.com")
    assert "/verify-email#token=" in mail.text and len(code_of(mail)) == 6
    user = user_row(mail_client, "carol")
    assert (user.email, user.email_verified) == (None, False)
    assert mail_client.post("/auth/email/verify", json={"token": token_of(mail)}).status_code == 200
    assert user_row(mail_client, "carol").email == "carol@example.com"


def test_a_mail_failure_does_not_fail_the_registration(mail_client):
    mail_client.app.state.mailer.fail = True
    response = combined(mail_client, username="carol", password="Carols-Pass-1", email="carol@example.com")
    assert response.status_code == 201 and user_row(mail_client, "carol") is not None


def test_email_alone_is_not_a_sign_in_method(mail_client):
    response = combined(mail_client, email="carol@example.com")
    assert (response.status_code, response.json()) == (422, {"detail": "Choose at least one sign-in method"})
    assert mail_client.app.state.mailer.sent == []


def test_register_with_an_invalid_email_is_a_422(mail_client):
    response = combined(mail_client, username="carol", password="Carols-Pass-1", email="nope")
    assert response.status_code == 422 and response.json()["detail"].startswith("email:")
    assert user_row(mail_client, "carol") is None


def test_register_with_an_email_verified_elsewhere_still_succeeds_without_mail(mail_client):
    verified_account(mail_client)
    mail_client.cookies.clear()
    response = combined(mail_client, username="carol", password="Carols-Pass-1", email=EMAIL)
    assert response.status_code == 201 and sent_to(mail_client, EMAIL) == []


def test_register_with_email_while_email_is_disabled_still_works(client):
    response = combined(client, username="carol", password="Carols-Pass-1", email="carol@example.com")
    assert response.status_code == 201 and token_rows(client) == []


def test_registration_mail_flood_to_one_address_is_capped(mail_client):
    for i in range(5):
        combined(mail_client, username=f"user{i}", password="Carols-Pass-1", email="victim@example.com")
    assert len(sent_to(mail_client, "victim@example.com")) == 3


# --- disabled / config -------------------------------------------------------------------------


def test_config_reports_email_enabled(client, mail_client):
    assert client.get("/auth/config").json()["email_enabled"] is False
    assert mail_client.get("/auth/config").json()["email_enabled"] is True


DISABLED_ROUTES = [
    ("post", "/auth/email/verify", {"token": "x"}),
    ("post", "/auth/email/login/request", {"email": EMAIL}),
    ("post", "/auth/email/login/verify", {"email": EMAIL, "code": "123456"}),
    ("post", "/auth/email/login/magic", {"token": "x"}),
    ("post", "/auth/password/forgot", {"email": EMAIL}),
    ("post", "/auth/password/reset", {"token": "x", "new_password": STRONG}),
    ("post", "/auth/me/email", {"email": EMAIL}),
    ("delete", "/auth/me/email", None),
]


@pytest.mark.parametrize(("method", "path", "body"), DISABLED_ROUTES)
def test_email_routes_are_503_when_email_is_disabled(client, method, path, body):
    response = client.request(method.upper(), path, json=body)
    assert (response.status_code, response.json()) == (503, {"detail": "Email is not available"})


def test_settings_read_the_smtp_environment(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "t" * 40)
    assert Settings.from_env().email_enabled is False
    for name, value in {
        "SMTP_HOST": "mail.example", "SMTP_PORT": "2525", "SMTP_USER": "u", "SMTP_PASSWORD": "p",
        "SMTP_FROM": "Site <no-reply@example.com>", "SMTP_STARTTLS": "0", "PUBLIC_URL": "https://site.example/",
        "SMTP_ALLOW_PLAINTEXT_AUTH": "1",
    }.items():  # fmt: skip
        monkeypatch.setenv(name, value)
    s = Settings.from_env()
    assert (s.email_enabled, s.smtp_host, s.smtp_port, s.smtp_user, s.smtp_password) == (True, "mail.example", 2525, "u", "p")
    assert (s.smtp_from, s.smtp_starttls, s.public_url) == ("Site <no-reply@example.com>", False, "https://site.example")


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "t" * 40)
    monkeypatch.setenv("SMTP_HOST", "mail.example")
    s = Settings.from_env()
    assert (s.smtp_port, s.smtp_starttls, s.public_url) == (587, True, "http://localhost:8080")


def test_public_url_must_be_http(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "t" * 40)
    monkeypatch.setenv("PUBLIC_URL", "javascript:alert(1)")
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_create_app_builds_an_smtp_mailer_from_the_environment(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "mail.example")
    app = create_app("sqlite://")
    assert isinstance(app.state.mailer, SmtpMailer)
    assert create_app("sqlite://") is not None


def test_no_mailer_when_smtp_host_is_empty():
    assert create_app("sqlite://").state.mailer is None


# --- schema upgrade ----------------------------------------------------------------------------


def make_pre_email_db(path):
    """The schema before email_verified existed, with a Google user, an email-less user and a plain email."""
    url = make_old_db(path)
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("ALTER TABLE users ADD COLUMN email VARCHAR(254)"))
        conn.execute(sa.text("ALTER TABLE users ADD COLUMN google_sub VARCHAR(64)"))
        insert = "INSERT INTO users (username, password_hash, created_at, email, google_sub) VALUES (:u, '!', '2024', :e, :g)"
        conn.execute(sa.text(insert), {"u": "gina", "e": "gina@example.com", "g": "sub-gina"})
        conn.execute(sa.text(insert), {"u": "plain", "e": "plain@example.com", "g": None})
        conn.execute(sa.text(insert), {"u": "nogoogleemail", "e": None, "g": "sub-x"})
    engine.dispose()
    return url


def verified_flags(engine):
    with engine.connect() as conn:
        return dict(conn.execute(sa.text("SELECT username, email_verified FROM users")).all())


def test_email_verified_is_added_and_google_emails_become_verified(tmp_path):
    engine = make_engine(make_pre_email_db(tmp_path / "pre.db"))

    added = ensure_columns(engine)

    assert "email_verified" in added
    column = {c["name"]: c for c in sa.inspect(engine).get_columns("users")}["email_verified"]
    assert not column["nullable"]
    assert verified_flags(engine) == {"olduser": 0, "gina": 1, "plain": 0, "nogoogleemail": 0}


def test_the_data_step_runs_only_when_the_column_is_first_created(tmp_path):
    engine = make_engine(make_pre_email_db(tmp_path / "pre.db"))
    ensure_columns(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET email_verified = 0 WHERE username = 'gina'"))

    assert ensure_columns(engine) == []

    assert verified_flags(engine)["gina"] == 0


def test_a_fully_old_database_gets_the_column_too(tmp_path):
    engine = make_engine(make_old_db(tmp_path / "old.db"))
    assert "email_verified" in ensure_columns(engine)
    assert verified_flags(engine) == {"olduser": 0}


def flag_values(engine):
    with engine.connect() as conn:
        return dict(conn.execute(sa.text("SELECT username, email_from_google FROM users")).all())


def test_email_from_google_is_added_and_google_addresses_are_flagged(tmp_path):
    engine = make_engine(make_pre_email_db(tmp_path / "pre.db"))

    added = ensure_columns(engine)

    assert "email_from_google" in added
    column = {c["name"]: c for c in sa.inspect(engine).get_columns("users")}["email_from_google"]
    assert not column["nullable"]
    assert flag_values(engine) == {"olduser": 0, "gina": 1, "plain": 0, "nogoogleemail": 0}


def test_the_email_from_google_data_step_runs_only_once(tmp_path):
    engine = make_engine(make_pre_email_db(tmp_path / "pre.db"))
    ensure_columns(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET email_from_google = 0 WHERE username = 'gina'"))

    assert ensure_columns(engine) == []

    assert flag_values(engine)["gina"] == 0


def test_app_starts_on_an_old_database_and_creates_the_token_table(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    app = create_app(make_pre_email_db(tmp_path / "pre.db"))
    with TestClient(app):
        assert "verification_codes" in sa.inspect(app.state.session_factory.kw["bind"]).get_table_names()
