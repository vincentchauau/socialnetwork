"""Thẻ sự kiện ngẫu nhiên mỗi đêm: đổi luật nhẹ trong đêm đó (hoặc ngày hôm sau) để mỗi ván khác nhau."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

import logging
logger = logging.getLogger(__name__)

EVENT_CHANCE = 0.5  # chance that a night has an event card


@dataclass(frozen=True)
class NightEvent:
    code: str
    icon: str
    title: str
    text: str
    affects_day: bool = False  # True: still in effect the next day

    def view(self) -> dict[str, Any]:
        try:
            return {"code": self.code, "icon": self.icon, "title": self.title, "text": self.text,
                    "affectsDay": self.affects_day}
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("view failed")
            raise


FOG = NightEvent("FOG", "🌫️", "Sương mù",
                 "Đêm nay Xem nhóm và Xem chức năng không cho kết quả.")
PEACEFUL = NightEvent("PEACEFUL", "🕊️", "Đêm bình yên",
                      "Đêm nay vote giết của Sói không có hiệu lực (Giết trực tiếp vẫn dùng được).")
BLOOD_MOON = NightEvent("BLOOD_MOON", "🩸", "Trăng máu",
                        "Vote giết của Sói hòa phiếu thì chọn ngẫu nhiên một trong những người nhiều phiếu nhất.")
FULL_MOON = NightEvent("FULL_MOON", "🌕", "Trăng tròn",
                       "Đêm nay Chống mọi hiệu ứng và Đảo ngược hiệu ứng mất tác dụng.")
GHOST_NIGHT = NightEvent("GHOST_NIGHT", "👻", "Đêm ma quái",
                         "Biến hình của Ma không thể bị chặn bởi bảo vệ hay phản đòn.")
JUSTICE = NightEvent("JUSTICE", "⚖️", "Ngày công lý",
                     "Ngày mai nếu hòa phiếu thì treo cổ ngẫu nhiên một trong những người hòa.", affects_day=True)

ALL_EVENTS: tuple[NightEvent, ...] = (FOG, PEACEFUL, BLOOD_MOON, FULL_MOON, GHOST_NIGHT, JUSTICE)


def draw_event() -> NightEvent | None:
    """Rút một thẻ cho đêm mới, hoặc không có thẻ nào (xác suất 1 - EVENT_CHANCE)."""
    try:
        if random.random() >= EVENT_CHANCE:
            return None
        return random.choice(ALL_EVENTS)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("draw_event failed")
        raise
