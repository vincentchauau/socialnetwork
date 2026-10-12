"""Helpers for the email tests: read what the fake mailer received and drive the verification flow."""

import re
from datetime import timedelta

from sqlalchemy import select, update

from app.models import EmailToken, User, utcnow
from tests.helpers import CREDS, csrf, register

EMAIL = "alice@example.com"
PUBLIC_URL = "https://app.example"
PW = {"password": CREDS["password"]}


def sent_to(client, address):
    return client.app.state.mailer.to(address)


def last_mail(client, address):
    messages = sent_to(client, address)
    assert messages, f"no mail was sent to {address}"
    return messages[-1]


def token_of(message) -> str:
    return re.search(r"#token=([\w-]+)", message.text).group(1)


def link_of(message) -> str:
    return re.search(r"https?://\S+", message.text).group(0)


def code_of(message) -> str:
    return re.search(r"(?<![\w-])(\d{6})(?![\w-])", message.text).group(1)


def add_email(client, session, email=EMAIL, body=None):
    return client.post("/auth/me/email", json={"email": email, **(PW if body is None else body)}, headers=csrf(session))


def verify_by_link(client, address):
    return client.post("/auth/email/verify", json={"token": token_of(last_mail(client, address))})


def verified_account(client, creds=CREDS, email=EMAIL):
    """A password account whose email is verified. Returns the session body (cookies are in the client)."""
    session = register(client, creds)
    assert add_email(client, session, email, {"password": creds["password"]}).status_code == 202
    assert verify_by_link(client, email).status_code == 200
    client.app.state.mailer.sent.clear()
    return session


def user_row(client, username="alice") -> User:
    with client.app.state.session_factory() as db:
        return db.scalar(select(User).where(User.username == username))


def token_rows(client) -> list[EmailToken]:
    with client.app.state.session_factory() as db:
        return list(db.scalars(select(EmailToken).order_by(EmailToken.id)))


def age_tokens(client, **delta):
    """Move every token's expiry into the past (default: one day)."""
    with client.app.state.session_factory() as db:
        db.execute(update(EmailToken).values(expires_at=utcnow() - timedelta(**(delta or {"days": 1}))))
        db.commit()


def set_user(client, username="alice", **columns):
    with client.app.state.session_factory() as db:
        db.execute(update(User).where(User.username == username).values(**columns))
        db.commit()
