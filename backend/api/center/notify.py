"""Queueing mail from request handlers: security notices and the link mails (always in the background)."""

from dataclasses import asdict

from fastapi import BackgroundTasks, Request

from api.center.mailer import Message, deliver
from api.center.mailtemplates import render
from api.center.methods import has_verified_email
from api.center.models import User


def _link(request: Request, path: str, token: str) -> str:
    """Links come from the PUBLIC_URL setting, never from the request (host-header poisoning).

    The token travels in the URL fragment: browsers never send it to a server, a log or a Referer header.
    """
    return f"{request.app.state.settings.public_url}{path}#token={token}"


def send_in_background(
    request: Request, background: BackgroundTasks, kind: str, to: str, **context: str | None
) -> None:
    """Render and send off the request path; the response never waits for or learns about the outcome."""
    mailer = request.app.state.mailer
    if mailer is None:
        return
    background.add_task(render_and_deliver, mailer, kind, to, context)


def render_and_deliver(mailer, kind: str, to: str, context: dict) -> None:
    deliver(mailer, Message(to=to, **asdict(render(kind, **context))), kind)


def notify(
    request: Request, background: BackgroundTasks, user: User, event: str, *, to: str | None = None, **context: str
) -> None:
    """Security notice to the user's VERIFIED address (or to `to`, an address the caller knows was verified)."""
    address = to or (user.email if has_verified_email(user) else None)
    if address:
        send_in_background(request, background, event, address, username=user.username, **context)


def send_link_mail(
    request: Request, background: BackgroundTasks, kind: str, to: str, token: str, code: str | None
) -> None:
    path = {"verify": "/verify-email", "login": "/login/magic", "reset": "/reset-password"}[kind]
    send_in_background(request, background, kind, to, link=_link(request, path, token), code=code)


def send_code_mail(request: Request, background: BackgroundTasks, kind: str, to: str, code: str) -> None:
    """A mail that carries only a code (no link)."""
    send_in_background(request, background, kind, to, code=code)
