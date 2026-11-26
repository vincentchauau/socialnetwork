"""Nhật ký chat trong ván: ba kênh (công khai ban ngày, riêng của Sói ban đêm, riêng của người chết)."""
from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass, field

MAX_LEN = 140
MIN_INTERVAL = 0.8  # giây giữa hai tin của cùng một người (chống spam)
KEEP = 400  # số tin giữ lại tối đa trong một ván
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
    dead: bool = False  # tác giả đã chết lúc gửi (hiện 💀 khi người chết chat chung)
    target: int = 0  # 0 = không nhắm ai; khác 0 = tin nhắn nói về người chơi này ("nghi X")


# Ký tự điều khiển và ký tự đổi chiều chữ / vô hình (dùng để giả mạo hiển thị); giữ ZWJ và variation selector cho emoji.
STRIPPED = {0x200B, 0x200E, 0x200F, 0x2028, 0x2029, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
             0x2060, 0x2066, 0x2067, 0x2068, 0x2069, 0xFEFF, 0x061C}


def clean(text: str) -> str:
    """Bỏ ký tự điều khiển, gộp khoảng trắng, cắt hai đầu; từ chối tin rỗng hoặc quá dài.

    Nội dung luôn là văn bản thuần: server không escape HTML, client phải hiển thị như text (không innerHTML).
    """
    text = "".join(c for c in text if c.isspace() or (unicodedata.category(c) != "Cc" and ord(c) not in STRIPPED))
    text = " ".join(text.split())
    if not text:
        raise ChatError("Tin nhắn không được để trống")
    if len(text) > MAX_LEN:
        raise ChatError(f"Tin nhắn tối đa {MAX_LEN} ký tự")
    return text


@dataclass
class Chat:
    messages: list[ChatMessage] = field(default_factory=list)
    _last: dict[int, float] = field(default_factory=dict)
    _seq: int = 0  # tăng dần, không dùng độ dài danh sách vì tin cũ có thể bị cắt bớt

    def add(self, author: int, channel: str, text: str, round_label: str, target: int = 0,
            now: float | None = None, throttle: bool = True, dead: bool = False) -> ChatMessage:
        """Thêm một tin. `throttle=False` dành cho bot (không bị giới hạn tốc độ)."""
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
