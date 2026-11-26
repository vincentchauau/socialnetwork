"""Pluggable SMS senders: `send(phone, text)`; a failure raises and the caller logs the class name only.

- mailbox: DEV ONLY, mails the text to `<digits>@sms.local` through the normal mailer (visible in Mailpit);
- twilio: the Twilio Messages REST API (not verifiable without a live account).
"""

import httpx

from api.center.config import ConfigError, Settings
from api.center.mailer import Mailer, Message
from api.center.mailtemplates import APP_NAME
from typing import Protocol

import logging
logger = logging.getLogger(__name__)

TWILIO_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
TWILIO_TIMEOUT_SECONDS = 5.0


class SmsProvider(Protocol):
    def send(self, phone: str, text: str) -> None: ...


class MailboxSms:
    def __init__(self, mailer: Mailer | None) -> None:
        try:
            self._mailer = mailer
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    def send(self, phone: str, text: str) -> None:
        try:
            if self._mailer is None:
                return
            digits = "".join(c for c in phone if c.isdigit())
            self._mailer.send(Message(to=f"{digits}@sms.local", subject=f"SMS - {APP_NAME}", text=text, html=f"<p>{text}</p>"))
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("send failed")
            raise


class TwilioSms:
    def __init__(self, sid: str, token: str, sender: str, *, transport: httpx.BaseTransport | None = None) -> None:
        try:
            self._sid, self._token, self._from = sid, token, sender
            self._transport = transport
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    def send(self, phone: str, text: str) -> None:
        try:
            with httpx.Client(timeout=TWILIO_TIMEOUT_SECONDS, transport=self._transport) as client:
                response = client.post(
                    TWILIO_URL.format(sid=self._sid), auth=(self._sid, self._token),
                    data={"To": phone, "From": self._from, "Body": text},
                )
                response.raise_for_status()
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("send failed")
            raise


def make_provider(settings: Settings, mailer: Mailer | None) -> SmsProvider | None:
    try:
        if settings.sms_provider == "":
            return None
        if settings.sms_provider == "mailbox":
            if settings.production:
                raise ConfigError("SMS_PROVIDER=mailbox is for development only")
            return MailboxSms(mailer)
        if settings.sms_provider == "twilio":
            return TwilioSms(settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_from)
        raise ConfigError("SMS_PROVIDER must be empty, 'mailbox' or 'twilio'")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("make_provider failed")
        raise
