"""Outgoing mail: a `Mailer` protocol, the SMTP implementation and a failure-proof `deliver`.

Failures are logged by exception type only (never the text of the error, which may carry hosts or
addresses) and never reach the client. Addresses are masked in every log line.
"""

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Protocol

from api.center.audit import audit

SMTP_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    text: str
    html: str


class Mailer(Protocol):
    def send(self, message: Message) -> None: ...


def mask_email(address: str | None) -> str:
    """`alice@example.com` -> `a***@e***.com`: enough to recognise it, not to reuse it."""
    if not address or "@" not in address:
        return "***"
    local, _, domain = address.rpartition("@")
    if not local or not domain:
        return "***"
    host, dot, tld = domain.rpartition(".")
    masked_domain = f"{host[:1]}***{dot}{tld}" if host else f"{tld[:1]}***"
    return f"{local[:1]}***@{masked_domain}"


class SmtpMailer:
    def __init__(
        self, host: str, port: int, user: str, password: str, sender: str, *, starttls: bool,
        use_ssl: bool = False, timeout: float = SMTP_TIMEOUT_SECONDS,
    ) -> None:  # fmt: skip
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sender, self.starttls, self.use_ssl, self.timeout = sender, starttls, use_ssl, timeout

    def _build(self, message: Message) -> EmailMessage:
        built = EmailMessage()
        built["From"] = self.sender
        built["To"] = message.to
        built["Subject"] = message.subject
        built.set_content(message.text, charset="utf-8", cte="quoted-printable")
        built.add_alternative(message.html, subtype="html", charset="utf-8", cte="quoted-printable")
        return built

    def send(self, message: Message) -> None:
        envelope_from = parseaddr(self.sender)[1] or self.sender
        if self.use_ssl:  # implicit TLS (port 465): the connection is encrypted from the first byte
            server_cm = smtplib.SMTP_SSL(
                self.host, self.port, timeout=self.timeout, context=ssl.create_default_context()
            )
        else:
            server_cm = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        with server_cm as server:
            if self.starttls and not self.use_ssl:
                server.starttls(context=ssl.create_default_context())
            if self.user:
                server.login(self.user, self.password)
            server.send_message(self._build(message), from_addr=envelope_from, to_addrs=[message.to])


def deliver(mailer: Mailer, message: Message, kind: str) -> None:
    """Send in the background; any failure is swallowed and logged by type."""
    try:
        mailer.send(message)
    except Exception as exc:  # noqa: BLE001 - a mail problem must never reach the client
        audit.warning("mail failed kind=%s to=%s error=%s", kind, mask_email(message.to), type(exc).__name__)
    else:
        audit.info("mail sent kind=%s to=%s", kind, mask_email(message.to))
