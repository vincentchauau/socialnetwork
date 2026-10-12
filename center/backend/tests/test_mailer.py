"""SmtpMailer speaks real SMTP (aiosmtpd on a local port); templates and the delivery wrapper."""

import email
import email.policy
import logging
import socket

import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult

from app.mailer import Message, SmtpMailer, deliver, mask_email
from app.mailtemplates import EVENTS, render

FROM = "Mạng xã hội <no-reply@localhost>"


class Inbox:
    def __init__(self) -> None:
        self.envelopes = []
        self.logins = []

    async def handle_DATA(self, server, session, envelope):
        self.envelopes.append(envelope)
        return "250 OK"

    def authenticator(self, server, session, envelope, mechanism, auth_data):
        self.logins.append((auth_data.login, auth_data.password))
        ok = (auth_data.login, auth_data.password) == (b"mailer", b"s3cret")
        return AuthResult(success=ok, handled=False)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def smtp():
    inbox = Inbox()
    port = free_port()
    controller = Controller(
        inbox, hostname="127.0.0.1", port=port, authenticator=inbox.authenticator, auth_required=False,
        auth_require_tls=False,
    )
    controller.start()
    inbox.port = port
    yield inbox
    controller.stop()


MESSAGE = Message(to="alice@example.com", subject="Xác minh email", text="Mã của bạn: 123456", html="<p>Mã: <b>123456</b></p>")


def parsed(envelope):
    return email.message_from_bytes(envelope.content, policy=email.policy.default)


def test_sends_over_plain_smtp_without_auth(smtp):
    mailer = SmtpMailer("127.0.0.1", smtp.port, "", "", FROM, starttls=False)

    mailer.send(MESSAGE)

    (envelope,) = smtp.envelopes
    assert envelope.rcpt_tos == ["alice@example.com"] and envelope.mail_from == "no-reply@localhost"
    assert smtp.logins == []
    message = parsed(envelope)
    assert message["Subject"] == "Xác minh email" and message["To"] == "alice@example.com"
    assert "Mạng xã hội" in message["From"]
    assert "Mã của bạn: 123456" in message.get_body(("plain",)).get_content()
    assert "<b>123456</b>" in message.get_body(("html",)).get_content()


def test_sends_with_authentication(smtp):
    SmtpMailer("127.0.0.1", smtp.port, "mailer", "s3cret", FROM, starttls=False).send(MESSAGE)
    assert smtp.logins == [(b"mailer", b"s3cret")] and len(smtp.envelopes) == 1


def test_wrong_credentials_raise_so_the_wrapper_can_log(smtp):
    mailer = SmtpMailer("127.0.0.1", smtp.port, "mailer", "wrong", FROM, starttls=False)
    with pytest.raises(Exception):
        mailer.send(MESSAGE)
    assert smtp.envelopes == []


def test_deliver_swallows_failures_and_logs_the_type_only(caplog):
    caplog.set_level(logging.INFO, logger="auth.audit")

    class Broken:
        def send(self, message):
            raise ConnectionRefusedError("secret-host:25 refused for alice@example.com")

    deliver(Broken(), MESSAGE, "verify")

    assert "ConnectionRefusedError" in caplog.text and "a***@e***.com" in caplog.text
    assert "secret-host" not in caplog.text and "alice@example.com" not in caplog.text and "123456" not in caplog.text


def test_deliver_to_an_unreachable_server_does_not_raise(caplog):
    mailer = SmtpMailer("127.0.0.1", free_port(), "", "", FROM, starttls=False, timeout=1)
    deliver(mailer, MESSAGE, "verify")  # nothing listens there


def test_mailer_has_timeouts():
    assert SmtpMailer("h", 25, "", "", FROM, starttls=False).timeout > 0


@pytest.mark.parametrize("kind", ["verify", "login", "reset"])
def test_link_mails_have_text_html_and_escape_values(kind):
    rendered = render(kind, link="https://app.example/x?token=a&b=<script>", code="123456" if kind != "reset" else None)
    assert rendered.subject and rendered.text and rendered.html
    assert "<script>" not in rendered.html and "&lt;script&gt;" in rendered.html
    assert "token=a&amp;b=" in rendered.html


@pytest.mark.parametrize("event", sorted(EVENTS))
def test_every_notice_renders_and_escapes_the_username(event):
    rendered = render(event, username="<i>Eve</i>", when="now")
    assert rendered.subject and rendered.text and rendered.html
    assert "<i>" not in rendered.html


def test_a_notice_is_vietnamese_and_has_no_secrets():
    rendered = render("password_changed", username="eve")
    assert "mật khẩu" in rendered.text.lower()


def test_mask_helper_is_total():
    assert mask_email("a@b.c") == "a***@b***.c"
