"""Security hardening of the email features: code brute force, timing, atomic revocation, SMTP safety, Google email rules."""

import logging

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError

from app import emailtokens as et
from app import mailer as mailer_module
from app.config import Settings
from app.mailer import Message, SmtpMailer
from app.main import create_app
from app.methods import methods_lost_on_unlink, usable_methods
from app.models import User
from app.tokenversion import bump_token_version
from tests.helpers import CREDS, csrf, register, grant_fresh
from tests.mail_helpers import (
    EMAIL, PW, add_email, code_of, last_mail, set_user, token_of, token_rows, user_row, verified_account,
    verify_by_link,
)  # fmt: skip
from tests.test_email_login import ID_ENDPOINT, REQUEST, ask, from_ip, known_account
TOO_MANY = {"detail": "Too many attempts, try later"}
GINA = "sub-30|gina@example.com"


def wrong_code(code: str) -> str:
    return "000000" if code != "000000" else "111111"


# --- 4: code brute force across rows ---------------------------------------------------------------


def test_ten_failed_codes_per_address_block_further_code_submissions_across_rows(mail_client):
    known_account(mail_client)
    for _ in range(3):  # three live rows: each one alone would allow five guesses
        ask(mail_client, EMAIL)
    mail = last_mail(mail_client, EMAIL)
    wrong = wrong_code(code_of(mail))

    codes = [mail_client.post(ID_ENDPOINT, json={"email": EMAIL, "code": wrong}).status_code for _ in range(10)]
    blocked = mail_client.post(ID_ENDPOINT, json={"email": EMAIL, "code": code_of(mail)})

    assert codes == [401] * 10
    assert (blocked.status_code, blocked.json()) == (429, TOO_MANY)


def test_the_code_failure_counter_is_the_same_for_an_unknown_address(mail_client):
    known_account(mail_client)
    results = []
    for address in (EMAIL, "ghost@example.com"):
        visitor = from_ip(mail_client, "198.51.100.20" if address == EMAIL else "198.51.100.21")
        results.append([visitor.post(ID_ENDPOINT, json={"email": address, "code": "000000"}).status_code for _ in range(11)])
    assert results[0] == results[1] == [401] * 10 + [429]


def test_the_failure_counter_is_per_address(mail_client):
    for _ in range(10):
        mail_client.post(ID_ENDPOINT, json={"email": "ghost@example.com", "code": "000000"})
    assert mail_client.post(ID_ENDPOINT, json={"email": "other@example.com", "code": "000000"}).status_code == 401


def test_verify_by_code_failures_are_capped_too(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    mail = last_mail(mail_client, EMAIL)
    wrong = wrong_code(code_of(mail))
    codes = [mail_client.post("/auth/email/verify", json={"code": wrong}).status_code for _ in range(10)]
    assert codes == [400] * 10
    blocked = mail_client.post("/auth/email/verify", json={"code": code_of(mail)})
    assert (blocked.status_code, blocked.json()) == (429, TOO_MANY)
    assert verify_by_link(mail_client, EMAIL).status_code == 200  # the link is not a code submission


def test_a_link_failure_is_not_counted_as_a_code_failure(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    for i in range(12):
        mail_client.post("/auth/email/verify", json={"token": f"nope{i}"})
    assert mail_client.post("/auth/email/verify", json={"code": code_of(last_mail(mail_client, EMAIL))}).status_code == 200


def test_find_for_user_skips_a_row_whose_code_is_burnt_but_the_link_finds_it(mail_client):
    session = register(mail_client)
    add_email(mail_client, session)
    mail = last_mail(mail_client, EMAIL)
    (row,) = token_rows(mail_client)
    with mail_client.app.state.session_factory() as db:
        assert et.find_for_user(db, row.user_id, et.VERIFY) is not None
        for _ in range(et.MAX_CODE_ATTEMPTS):
            et.check_code(db, et.find_for_user(db, row.user_id, et.VERIFY) or row, "x")
        assert et.find_for_user(db, row.user_id, et.VERIFY) is None
        assert et.find_by_token(db, token_of(mail), et.VERIFY) is not None


# --- 6: timing ----------------------------------------------------------------------------------


def test_known_and_unknown_requests_get_the_same_bounded_jitter(mail_client, monkeypatch):
    known_account(mail_client)
    sleeps = []
    monkeypatch.setattr("app.routes_email.time.sleep", sleeps.append)
    ask(mail_client, EMAIL)
    ask(mail_client, "ghost@example.com")
    assert len(sleeps) == 2 and all(0 <= s <= 0.030 for s in sleeps)


def statements(client, action):
    engine, seen = client.app.state.session_factory.kw["bind"], []
    listener = lambda conn, cursor, statement, *args: seen.append(" ".join(statement.split()[:3]))  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        action()
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return [s for s in seen if s.startswith(("INSERT", "UPDATE", "DELETE"))]


def test_the_unknown_path_does_the_same_writes_but_stores_nothing(mail_client):
    known_account(mail_client)
    known = statements(mail_client, lambda: ask(mail_client, EMAIL))
    rows_after_known = len(token_rows(mail_client))
    unknown = statements(mail_client, lambda: ask(mail_client, "ghost@example.com"))
    assert unknown == known and any("INSERT" in s for s in unknown)
    assert len(token_rows(mail_client)) == rows_after_known  # the rehearsal was rolled back


def test_the_unknown_path_survives_an_empty_database_and_an_unstorable_placeholder(mail_client, monkeypatch):
    assert ask(mail_client, "ghost@example.com").status_code == 202  # no users at all: nothing to rehearse with
    known_account(mail_client)

    def refuse(*_):
        raise IntegrityError("insert", {}, Exception("fk"))

    monkeypatch.setattr(et, "_insert", refuse)
    assert ask(mail_client, "ghost@example.com").json() == {"ok": True}
    assert token_rows(mail_client) == []


# --- 8: atomic token_version ------------------------------------------------------------------------


def test_two_interleaved_bumps_are_two_bumps(mail_file_client):
    client = mail_file_client
    register(client)
    before = user_row(client).token_version
    factory = client.app.state.session_factory
    with factory() as first, factory() as second:
        a = first.scalar(select(User).where(User.username == "alice"))
        b = second.scalar(select(User).where(User.username == "alice"))  # both read the same stale version
        bump_token_version(first, a)
        first.commit()
        bump_token_version(second, b)
        second.commit()
        assert (a.token_version, b.token_version) == (before + 1, before + 2)
    assert user_row(client).token_version == before + 2


def test_a_bump_does_not_discard_pending_changes_on_the_instance(mail_client):
    register(mail_client)
    with mail_client.app.state.session_factory() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        user.role = "admin"
        bump_token_version(db, user)
        db.commit()
    assert user_row(mail_client).role == "admin"


def test_logout_and_password_change_bump_by_exactly_one(mail_client):
    session = register(mail_client)
    start = user_row(mail_client).token_version
    changed = mail_client.post(
        "/auth/me/password", json={"current_password": CREDS["password"], "new_password": "brand-new-pass-9"},
        headers=csrf(session),
    )
    assert user_row(mail_client).token_version == start + 1
    assert mail_client.post("/auth/logout", headers=csrf(changed.json())).status_code == 204
    assert user_row(mail_client).token_version == start + 2


# --- 7: SMTP ------------------------------------------------------------------------------------------


def smtp_env(monkeypatch, **values):
    monkeypatch.setenv("JWT_SECRET", "t" * 40)
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return Settings.from_env()


def test_credentials_without_tls_to_a_remote_host_disable_email(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger="auth.audit")
    monkeypatch.setenv("SMTP_HOST", "smtp.remote.example")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_STARTTLS", "0")
    settings = smtp_env(monkeypatch)
    assert settings.email_enabled is False and "email disabled" in caplog.text
    assert create_app("sqlite://").state.mailer is None


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "mailpit", "MailPit"])
def test_credentials_without_tls_are_fine_on_a_local_host(monkeypatch, host):
    assert smtp_env(monkeypatch, SMTP_HOST=host, SMTP_USER="u", SMTP_STARTTLS="0").email_enabled is True


def test_plaintext_auth_can_be_allowed_explicitly(monkeypatch):
    settings = smtp_env(
        monkeypatch, SMTP_HOST="smtp.remote.example", SMTP_USER="u", SMTP_STARTTLS="0", SMTP_ALLOW_PLAINTEXT_AUTH="1"
    )
    assert settings.email_enabled is True


@pytest.mark.parametrize("extra", [{}, {"SMTP_STARTTLS": "1"}, {"SMTP_SSL": "1", "SMTP_STARTTLS": "0"}, {"SMTP_USER": ""}])
def test_tls_or_no_credentials_keep_email_enabled(monkeypatch, extra):
    env = {"SMTP_HOST": "smtp.remote.example", "SMTP_USER": "u", "SMTP_STARTTLS": "0", **extra}
    if "SMTP_STARTTLS" not in extra and "SMTP_SSL" not in extra and "SMTP_USER" not in extra:
        env["SMTP_STARTTLS"] = "1"
    assert smtp_env(monkeypatch, **env).email_enabled is True


def test_smtp_ssl_defaults_to_port_465_and_can_be_overridden(monkeypatch):
    assert smtp_env(monkeypatch, SMTP_HOST="mail.example", SMTP_SSL="1").smtp_port == 465
    assert smtp_env(monkeypatch, SMTP_HOST="mail.example", SMTP_SSL="1", SMTP_PORT="2465").smtp_port == 2465
    monkeypatch.delenv("SMTP_SSL")
    monkeypatch.delenv("SMTP_PORT")
    plain = smtp_env(monkeypatch, SMTP_HOST="mail.example")
    assert (plain.smtp_ssl, plain.smtp_port) == (False, 587)


def test_smtp_ssl_mode_uses_implicit_tls_with_a_default_context(monkeypatch):
    calls = []

    class FakeSslServer:
        def __init__(self, host, port, timeout=None, context=None):
            calls.append(("init", host, port, timeout, context))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, **kwargs):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, message, from_addr, to_addrs):
            calls.append(("send", from_addr, tuple(to_addrs)))

    monkeypatch.setattr(mailer_module.smtplib, "SMTP_SSL", FakeSslServer)
    monkeypatch.setattr(mailer_module.smtplib, "SMTP", lambda *a, **k: pytest.fail("plain SMTP used in SSL mode"))
    mailer = SmtpMailer("mail.example", 465, "u", "p", "Site <no-reply@example.com>", starttls=True, use_ssl=True)

    mailer.send(Message(to="a@example.com", subject="s", text="t", html="<p>t</p>"))

    kind, host, port, timeout, context = calls[0]
    assert (host, port) == ("mail.example", 465) and timeout > 0
    assert context is not None and context.verify_mode.name == "CERT_REQUIRED" and context.check_hostname
    assert [c[0] for c in calls[1:]] == ["login", "send"]  # no STARTTLS on top of implicit TLS


def test_create_app_passes_ssl_mode_to_the_mailer(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "mail.example")
    monkeypatch.setenv("SMTP_SSL", "1")
    assert create_app("sqlite://").state.mailer.use_ssl is True


# --- 9: email_from_google ------------------------------------------------------------------------------


def link_google(client, session, token, password=True):
    body = {"id_token": token, **(PW if password else {})}
    return client.post("/auth/me/google", json=body, headers=csrf(session))


def test_google_sign_up_marks_the_address_as_googles(mail_client):
    mail_client.post("/auth/google", json={"id_token": GINA})
    user = user_row(mail_client, "gina")
    assert (user.email, user.email_verified, user.email_from_google) == ("gina@example.com", True, True)


def test_google_sign_up_with_a_taken_address_sets_no_flag(mail_client):
    verified_account(mail_client, email="gina@example.com")
    mail_client.cookies.clear()
    mail_client.post("/auth/google", json={"id_token": GINA})
    with mail_client.app.state.session_factory() as db:
        user = db.scalar(select(User).where(User.google_sub == "sub-30"))
    assert (user.email, user.email_from_google) == (None, False)


def test_combined_registration_with_google_marks_the_address_as_googles(mail_client):
    response = mail_client.post("/auth/register/combined", data={"google_id_token": "sub-31|reg@example.com"})
    assert response.status_code == 201
    with mail_client.app.state.session_factory() as db:
        user = db.scalar(select(User).where(User.google_sub == "sub-31"))
    assert (user.email, user.email_from_google) == ("reg@example.com", True)


def test_linking_google_sets_the_flag_only_when_google_wrote_the_address(mail_client):
    session = register(mail_client)
    assert link_google(mail_client, session, "sub-32|fresh@example.com").status_code == 200
    user = user_row(mail_client)
    assert (user.email, user.email_verified, user.email_from_google) == ("fresh@example.com", True, True)


def test_linking_google_never_overwrites_a_verified_address_and_leaves_the_flag_off(mail_client):
    session = verified_account(mail_client)
    assert link_google(mail_client, session, "sub-33|other@example.com").status_code == 200
    user = user_row(mail_client)
    assert (user.email, user.email_verified, user.email_from_google) == (EMAIL, True, False)


def test_linking_google_with_the_users_own_unverified_address_does_not_claim_it(mail_client):
    session = register(mail_client)
    set_user(mail_client, email="mine@example.com", email_verified=False)
    assert link_google(mail_client, session, "sub-34|mine@example.com").status_code == 200
    user = user_row(mail_client)
    assert (user.email, user.email_verified, user.email_from_google) == ("mine@example.com", True, False)


def test_unlinking_google_keeps_an_address_the_user_verified(mail_client):
    session = verified_account(mail_client)
    link_google(mail_client, session, "sub-35|other@example.com")

    response = mail_client.request("DELETE", "/auth/me/google", json=PW, headers=csrf(session))

    assert response.status_code == 200
    assert (response.json()["email"], response.json()["email_verified"], response.json()["google_linked"]) == (EMAIL, True, False)
    user = user_row(mail_client)
    assert (user.email, user.email_verified, user.email_from_google) == (EMAIL, True, False)


def test_unlinking_google_removes_the_address_google_supplied_and_resets_the_flag(mail_client):
    session = register(mail_client)
    link_google(mail_client, session, "sub-36|fresh@example.com")

    response = mail_client.request("DELETE", "/auth/me/google", json=PW, headers=csrf(session))

    assert response.status_code == 200 and response.json()["email"] is None
    user = user_row(mail_client)
    assert (user.email, user.email_verified, user.email_from_google) == (None, False, False)


def test_verifying_a_different_address_takes_the_address_away_from_google(mail_client):
    mail_client.post("/auth/google", json={"id_token": GINA})
    session = mail_client.get("/auth/me").json()
    grant_fresh(mail_client)
    assert add_email(mail_client, session, "gina.own@example.com", body={}).status_code == 202
    assert verify_by_link(mail_client, "gina.own@example.com").status_code == 200
    user = user_row(mail_client, "gina")
    assert (user.email, user.email_from_google) == ("gina.own@example.com", False)

    # Google is the only other method, but the user's own verified address now counts: unlinking is allowed
    response = mail_client.request("DELETE", "/auth/me/google", headers=csrf(session))
    assert response.status_code == 200 and response.json()["email"] == "gina.own@example.com"
    assert user_row(mail_client, "gina").email == "gina.own@example.com"


def test_verifying_the_same_address_keeps_the_flag(mail_client):
    mail_client.post("/auth/google", json={"id_token": GINA})
    session = mail_client.get("/auth/me").json()
    grant_fresh(mail_client)
    add_email(mail_client, session, "gina@example.com", body={})
    assert verify_by_link(mail_client, "gina@example.com").status_code == 200
    assert user_row(mail_client, "gina").email_from_google is True


def test_removing_the_address_resets_the_flag(mail_client):
    session = register(mail_client)
    link_google(mail_client, session, "sub-37|fresh@example.com")
    response = mail_client.request("DELETE", "/auth/me/email", json=PW, headers=csrf(session))
    assert response.status_code == 200
    assert user_row(mail_client).email_from_google is False


def test_the_last_method_guard_follows_the_flag(mail_client):
    flagged = User(username="x", password_hash="!", google_sub="g", email=EMAIL, email_verified=True, email_from_google=True)
    own = User(username="y", password_hash="!", google_sub="g", email=EMAIL, email_verified=True, email_from_google=False)
    assert methods_lost_on_unlink(flagged) == ("google", "email")
    assert methods_lost_on_unlink(own) == ("google",)
    assert usable_methods(flagged, without=methods_lost_on_unlink(flagged)) == 0
    assert usable_methods(own, without=methods_lost_on_unlink(own)) == 1


def test_a_google_only_account_with_its_own_verified_address_may_unlink(mail_client):
    mail_client.post("/auth/google", json={"id_token": GINA})
    session = mail_client.get("/auth/me").json()
    grant_fresh(mail_client)
    set_user(mail_client, "gina", email_from_google=False)  # the address is the user's own
    response = mail_client.request("DELETE", "/auth/me/google", headers=csrf(session))
    assert response.status_code == 200 and response.json()["email_verified"] is True
