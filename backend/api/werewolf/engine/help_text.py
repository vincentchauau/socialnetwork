"""Nội dung giải thích luật và chức năng cho giao diện (bảng trợ giúp)."""
from __future__ import annotations

from api.werewolf.engine.events import ALL_EVENTS
from api.werewolf.engine.roles import Ability

import logging
logger = logging.getLogger(__name__)

ABILITY_HELP: dict[Ability, str] = {
    Ability.NONE: "Người thường: không có chức năng đặc biệt. Chỉ có vote ban ngày, hãy quan sát và thuyết phục mọi người.",
    Ability.KILL: "Mỗi đêm chọn 1 người để giết. Bị chặn nếu mục tiêu được bảo vệ; nếu mục tiêu có phản đòn thì bạn chết thay.",
    Ability.KILL_ON_DEATH: "Bị động. Khi bạn chết (kể cả bị treo cổ), bạn kéo theo 1 người thuộc phe khác chết cùng.",
    Ability.BLOCK_EFFECTS: "Mỗi đêm bảo vệ 1 người khỏi bị giết, bị vote giết và bị biến hình. Không bảo vệ cùng một người 2 đêm liên tiếp.",
    Ability.REVERSE_EFFECTS: "Đặt phản đòn lên 1 người: ai tấn công họ đêm đó sẽ chịu lại đòn của chính mình.",
    Ability.BLOCK_ABILITY: "Khóa 1 người: họ mất toàn bộ hành động đêm đó (kể cả vote giết ban đêm của Sói).",
    Ability.REVERSE_ABILITY: "Hành động của 1 người đêm đó quay về chính họ (tự giết mình, tự bảo vệ mình...).",
    Ability.SEE_FACTION: "Mỗi đêm biết 1 người thuộc phe Người, Sói hay Ma. Kết quả công khai (không nêu người soi); riêng Sói soi thì chỉ Sói biết.",
    Ability.SEE_ABILITY: "Mỗi đêm biết chức năng của 1 người. Kết quả công khai; riêng Sói soi thì chỉ Sói biết.",
    Ability.REVEAL_ON_DEATH: "Bị động. Khi bạn chết, phe và chức năng của bạn được công khai.",
    Ability.TRANSFORM: "Mỗi đêm biến 1 người (Người hoặc Sói) thành Ma. Bị chặn nếu mục tiêu được bảo vệ hoặc có phản đòn.",
}

RULES: list[dict[str, str]] = [
    {"icon": "🌙", "title": "Ban đêm",
     "text": "Ai có chức năng thì dùng lên 1 người. Mỗi Sói còn có vote giết chung: người nhiều phiếu nhất bị giết (hòa phiếu thì không ai chết)."},
    {"icon": "☀️", "title": "Ban ngày",
     "text": "Thảo luận rồi cả làng vote treo cổ 1 người. Hòa phiếu hoặc bỏ trắng hết thì không ai bị treo."},
    {"icon": "🏆", "title": "Thắng thua",
     "text": "Người thắng khi hết Sói. Sói thắng khi số Sói ≥ số Người. Ma thắng khi chiếm ít nhất nửa số người sống. Không còn ai sống thì hòa."},
    {"icon": "🗳", "title": "Vote mặc định",
     "text": "Ai cũng có vote ban ngày; Sói có thêm vote giết ban đêm; Ma có Biến hình. Tất cả đều có thể bỏ phiếu trắng."},
    {"icon": "💬", "title": "Chat",
     "text": "Ban ngày người sống chat công khai; ban đêm Sói chat riêng; người chết chat riêng với nhau."},
]


def help_payload() -> dict[str, object]:
    """Dữ liệu trợ giúp gửi cho client: luật chung và danh sách thẻ sự kiện."""
    try:
        return {"rules": RULES, "events": [e.view() for e in ALL_EVENTS]}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("help_payload failed")
        raise
