"""Bot biết nhớ và nghi ngờ: vote ban ngày dựa trên lịch sử vote/chat, Sói phối hợp, bot "nói chuyện" trong chat."""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

from api.werewolf.engine.roles import Ability, Faction

if TYPE_CHECKING:
    from api.werewolf.engine.game import Game, Player

BANDWAGON_CHANCE = 0.35  # bot không có manh mối thì có xác suất này theo phe đang dẫn đầu
CHATTER_CHANCE = 0.55  # xác suất một bot lên tiếng mỗi buổi sáng
THREATENING = (Ability.SEE_FACTION, Ability.SEE_ABILITY, Ability.KILL, Ability.BLOCK_ABILITY, Ability.REVERSE_ABILITY)
QUIET_LINES = (
    "😶 Tôi chưa có manh mối nào.",
    "🙏 Mọi người tin tôi, tôi là người tốt.",
    "🤷 Chưa ai đáng nghi lắm nhỉ?",
    "👀 Mình sẽ quan sát thêm.",
)


def suspicion(game: Game, bot: Player) -> dict[int, float]:
    """Điểm nghi ngờ của `bot` với từng người, từ các ngày đã qua và lời buộc tội trong chat."""
    know = game.knowledge_for(bot)
    scores: dict[int, float] = defaultdict(float)
    for votes in game.vote_history:
        for voter_id, target_id in votes.items():
            if voter_id == bot.id or not target_id:
                continue
            if target_id == bot.id:
                scores[voter_id] += 2.0  # từng vote mình
                continue
            target_faction = know.get(target_id, {}).get("faction")
            if target_faction == bot.faction:
                scores[voter_id] += 1.5  # vote đồng minh đã biết
            elif target_faction is not None:
                scores[voter_id] -= 2.0  # vote kẻ thù đã biết: đáng tin hơn
    for msg in game.chat.messages:
        if msg.channel == "public" and msg.target == bot.id and msg.author != bot.id:
            scores[msg.author] += 1.0  # đã buộc tội mình trong chat
    return scores


def wolf_day_target(game: Game) -> Player | None:
    """Mục tiêu chung của các Sói bot trong ngày (cả bầy cùng vote một người để dồn phiếu)."""
    if game._wolf_target_for == game.night:
        return game.player(game._wolf_target_id) if game._wolf_target_id else None
    wolves = {w.id for w in game.alive(Faction.WOLF)}
    candidates = [x for x in game.alive() if x.faction != Faction.WOLF]
    target = None
    if candidates:
        last_votes = game.vote_history[-1] if game.vote_history else {}
        weights = []
        for x in candidates:
            weight = 1.0
            if game.public_info.get(x.id, {}).get("ability") in THREATENING:
                weight += 3.0  # chức năng nguy hiểm đã bị lộ
            if last_votes.get(x.id) in wolves:
                weight += 2.0  # hôm qua đã vote một Sói
            weights.append(weight)
        target = random.choices(candidates, weights=weights)[0]
    game._wolf_target_for = game.night
    game._wolf_target_id = target.id if target else 0
    return target


def day_vote(game: Game, voter: Player, others: list[Player], cast: dict[int, int]) -> Player:
    """Chọn người để treo cổ. `cast`: các phiếu bot đã bỏ trước đó trong ngày (để theo phe đang dẫn đầu)."""
    know = game.knowledge_for(voter)
    exposed = [x for x in others if know.get(x.id, {}).get("faction") not in (None, voter.faction)]
    if exposed:
        return random.choice(exposed)
    if voter.faction == Faction.WOLF:
        target = wolf_day_target(game)
        if target is not None and target in others:
            return target
    if cast and random.random() < BANDWAGON_CHANCE:
        leader, _ = Counter(cast.values()).most_common(1)[0]
        pick = next((x for x in others if x.id == leader), None)
        if pick is not None:
            return pick
    scores = suspicion(game, voter)
    return max(others, key=lambda x: scores.get(x.id, 0.0) + random.random() * 0.5)


def chatter(game: Game) -> list[tuple[Player, str, int]]:
    """Những câu bot nói vào buổi sáng: (bot, nội dung, id người được nhắc tới hoặc 0)."""
    lines: list[tuple[Player, str, int]] = []
    alive = game.alive()
    for bot in alive:
        if not bot.is_bot or random.random() > CHATTER_CHANCE:
            continue
        others = [x for x in alive if x != bot]
        if not others:
            continue
        if bot.faction == Faction.WOLF:
            target = wolf_day_target(game)
            if target is not None:
                lines.append((bot, f"🤔 Tôi nghi {target.name} lắm, mọi người nghĩ sao?", target.id))
                continue
        know = game.knowledge_for(bot)
        exposed = [x for x in others if know.get(x.id, {}).get("faction") not in (None, bot.faction)]
        if exposed:
            x = random.choice(exposed)
            label = know[x.id]["faction"].value
            lines.append((bot, f"🔍 {x.name} thuộc phe {label}, vote đi!", x.id))
            continue
        scores = suspicion(game, bot)
        top = max(others, key=lambda x: scores.get(x.id, 0.0))
        if scores.get(top.id, 0.0) > 0:
            lines.append((bot, f"🤔 Tôi nghi {top.name}, bạn ấy hay vote tôi.", top.id))
        else:
            lines.append((bot, random.choice(QUIET_LINES), 0))
    return lines
