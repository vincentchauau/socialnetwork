"""The agent inside the chat: writes what a virtual person says, and runs the tools of the assistant.

It runs in the same process as the chat, so the chat calls these functions directly (no HTTP, no signature). The words are never posted
here: the chat saves them as the virtual person, so every rule of a room (muted, closed, blocked) still applies.

Limits, per caller and per hour, in memory (a restart gives a fresh hour): `AGENT_REPLIES_PER_HOUR` for replies and tool calls.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from sn_shared.directory import Person
from sqlalchemy.orm import Session

from api.chat.agent import tools
from api.chat.agent.models import persona_of
from api.chat.agent.providers import AgentError, Line, Provider, Usage, get_provider

logger = logging.getLogger(__name__)

log = logging.getLogger("chat.agent")

REPLIES_PER_CALLER_PER_HOUR = 120
HOUR_SECONDS = 3600.0


@dataclass(frozen=True)
class Reply:
    text: str
    usage: Usage
    ms: int  # how long the model took


class Limiter:
    """At most `limit` calls per caller per window."""

    def __init__(self, limit: int, window: float = HOUR_SECONDS) -> None:
        try:
            self.limit_routes, self._window = limit, window
            self._seen: dict[int, deque[float]] = defaultdict(deque)
            self.guard = threading.Lock()
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    def allow(self, key: int, now: float | None = None) -> bool:
        try:
            moment = now if now is not None else time.monotonic()
            with self.guard:
                seen = self._seen[key]
                while seen and moment - seen[0] > self._window:
                    seen.popleft()
                if len(seen) >= self.limit_routes:
                    return False
                seen.append(moment)
                return True
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("allow failed")
            raise


limiter_service = Limiter(int(os.environ.get("AGENT_REPLIES_PER_HOUR", REPLIES_PER_CALLER_PER_HOUR)))
provider_seed_other: Provider | None = None


def provider() -> Provider:
    """The model, chosen by `AI_PROVIDER` (dummy by default); built once."""
    try:
        global provider_seed_other
        if provider_seed_other is None:
            provider_seed_other = get_provider()
        return provider_seed_other
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("provider failed")
        raise


def reply(db: Session, virtual_id: int, caller_id: int, caller: str, history: list[Line]) -> Reply | None:
    """What the virtual person says to `caller` after `history`; None when it cannot (not a virtual person, limited, model failed)."""
    person = db.get(Person, virtual_id)
    if person is None or not person.is_virtual or not history:
        return None
    if not limiter_service.allow(caller_id):
        log.info("agent: replies limited for one caller")
        return None
    try:
        started = time.monotonic()
        text, usage = provider().reply_with_usage(persona_of(person), history, caller)
        ms = round((time.monotonic() - started) * 1000)
    except AgentError:
        log.warning("agent: the model did not answer")
        return None
    return Reply(text=text, usage=usage, ms=ms)


def run_tool(tool: str, args: dict[str, Any], caller_id: int, token: str, confirmed: bool, http: tools.Http = tools.send_request) -> dict[str, Any] | None:
    """The card of a tool run for the person (reads run; writes only when `confirmed`); None when it cannot run."""
    if not limiter_service.allow(caller_id):
        return None
    try:
        card = tools.run_tool(tool, args, token, confirmed, http)
    except (KeyError, ValueError, tools.ToolError):
        return None
    return card if isinstance(card, dict) else None
