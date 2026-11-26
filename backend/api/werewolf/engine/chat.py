"""Nhật ký chat trong ván: ba kênh (công khai ban ngày, riêng của Sói ban đêm, riêng của người chết)."""
from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass, field

import logging
logger = logging.getLogger(__name__)

MAX_LEN = 140
MIN_INTERVAL = 0.8  # seconds between two messages of the same person (anti-spam)
KEEP = 400  # maximum number of messages kept in one game
CHANNELS = ("public", "wolf", "dead")


class ChatError(ValueError):
    """Tin nhắn không hợp lệ (rỗng, quá dài, gửi quá nhanh...)."""


@dataclass(frozen=True)
class ChatMessage:
    seq: int
    round: str
    author: int
    channel: str
    text: str
    dead: bool = False  # the author was dead when sending (shows 💀 when the dead chat in the shared channel)
    target: int = 0  # 0 = targets nobody; otherwise the message is about this player ("suspect X")


# Control characters and invisible bidi characters (used to fake the display); keep ZWJ and variation selectors for emoji.
STRIPPED = {0x200B, 0x200E, 0x200F, 0x2028, 0x2029, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
             0x2060, 0x2066, 0x2067, 0x2068, 0x2069, 0xFEFF, 0x061C}


def clean(text: str) -> str:
    """Bỏ ký tự điều khiển, gộp khoảng trắng, cắt hai đầu; từ chối tin rỗng hoặc quá dài.

    Nội dung luôn là văn bản thuần: server không escape HTML, client phải hiển thị như text (không innerHTML).
    """
    try:
        text = "".join(c for c in text if c.isspace() or (unicodedata.category(c) != "Cc" and ord(c) not in STRIPPED))
        text = " ".join(text.split())
        if not text:
            raise ChatError("Tin nhắn không được để trống")
        if len(text) > MAX_LEN:
            raise ChatError(f"Tin nhắn tối đa {MAX_LEN} ký tự")
        return text
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("clean failed")
        raise


@dataclass
class Chat:
    messages: list[ChatMessage] = field(default_factory=list)
    _last: dict[int, float] = field(default_factory=dict)
    _seq: int = 0  # increases monotonically; not the list length, because old messages may be trimmed

    def add(self, author: int, channel: str, text: str, round_label: str, target: int = 0,
            now: float | None = None, throttle: bool = True, dead: bool = False) -> ChatMessage:
        """Thêm một tin. `throttle=False` dành cho bot (không bị giới hạn tốc độ)."""
        try:
            if channel not in CHANNELS:
                raise ChatError("Kênh chat không hợp lệ")
            text = clean(text)
            now = time.monotonic() if now is None else now
            if throttle and now - self._last.get(author, -1e9) < MIN_INTERVAL:
                raise ChatError("Bạn gửi quá nhanh, chờ một chút")
            if throttle:
                self._last[author] = now
            message = ChatMessage(self._seq, round_label, author, channel, text, dead, target)
            self._seq += 1
            self.messages.append(message)
            if len(self.messages) > KEEP:
                del self.messages[: len(self.messages) - KEEP]
            return message
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("add failed")
            raise
