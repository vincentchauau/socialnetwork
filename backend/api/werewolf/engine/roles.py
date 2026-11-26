"""Định nghĩa vai: phe, chức năng, giới hạn số lượng, cách chia ngẫu nhiên và kiểm tra bộ vai tự chỉnh."""
from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

MIN_PLAYERS = 5
MAX_PLAYERS = 40
THREE_FACTION_FROM = 12  # dưới ngưỡng này chỉ có 2 phe (Người, Sói), không có Ma


class Faction(Enum):
    VILLAGER = "Người"
    WOLF = "Sói"
    GHOST = "Ma"


class Ability(Enum):
    NONE = "Không có chức năng"  # người thường: chỉ có vote ban ngày
    BLOCK_EFFECTS = "Chống mọi hiệu ứng"
    REVERSE_EFFECTS = "Đảo ngược hiệu ứng"
    BLOCK_ABILITY = "Chống chức năng"
    REVERSE_ABILITY = "Đảo ngược chức năng"
    KILL = "Giết trực tiếp"
    KILL_ON_DEATH = "Giết khi chết"
    SEE_FACTION = "Xem nhóm"
    SEE_ABILITY = "Xem chức năng"
    REVEAL_ON_DEATH = "Lộ info khi chết"
    TRANSFORM = "Biến hình (Ma)"


class GameError(ValueError):
    """Hành động không hợp lệ (sai phase, sai mục tiêu...)."""


DEFENSIVE = [Ability.BLOCK_EFFECTS, Ability.REVERSE_EFFECTS]
DISRUPTIVE = [Ability.BLOCK_ABILITY, Ability.REVERSE_ABILITY]
INTEL = [Ability.SEE_FACTION, Ability.SEE_ABILITY, Ability.REVEAL_ON_DEATH]
PASSIVE = (Ability.NONE, Ability.KILL_ON_DEATH, Ability.REVEAL_ON_DEATH)

# Mỗi phe chỉ được chọn chức năng trong nhóm của phe đó. Vote giết ban đêm không phải chức năng:
# mọi Sói luôn có sẵn (xem wolf_options).
OFFENSIVE = [Ability.KILL, Ability.KILL_ON_DEATH]
ALLOWED_ABILITIES: dict[Faction, list[Ability]] = {
    Faction.VILLAGER: [Ability.NONE] + OFFENSIVE + DEFENSIVE + DISRUPTIVE + INTEL,
    Faction.WOLF: list(OFFENSIVE),  # Sói chỉ có chức năng tấn công (+ vote giết đêm mặc định)
    Faction.GHOST: [Ability.TRANSFORM],  # Ma chỉ có Biến hình
}

# Chức năng mặc định (không chọn được, hiển thị dạng nút bị khóa): người chơi nào cũng có vote ban ngày.
# `label` ngắn để hiện trên giao diện, `hint` là mô tả đầy đủ.
DAY_VOTE = {"icon": "🗳", "label": "Vote ngày",
             "hint": "Vote chết ban ngày (có thể bỏ phiếu trắng)"}
NIGHT_VOTE = {"icon": "🌙", "label": "Vote đêm",
               "hint": "Vote chết ban đêm của Sói (có thể bỏ phiếu trắng)"}
TRANSFORM_DEFAULT = {"icon": "✨", "label": "Biến hình",
                      "hint": "Mỗi đêm biến một người thành Ma"}
DEFAULT_ABILITIES: dict[Faction, list[dict[str, str]]] = {
    Faction.VILLAGER: [DAY_VOTE],
    Faction.WOLF: [NIGHT_VOTE, DAY_VOTE],
    Faction.GHOST: [TRANSFORM_DEFAULT, DAY_VOTE],
}


@dataclass(frozen=True)
class RoleCounts:
    """Số lượng từng loại vai lúc bắt đầu cho một phòng `m` người."""
    wolves: int  # Sói: luôn có chức năng tấn công
    holders: int  # Người có chức năng (tấn công / phòng thủ / gây rối / tình báo)
    ghosts: int  # Ma: chỉ có Biến hình
    plain: int  # Người thường: không có chức năng

    @property
    def villagers(self) -> int:
        return self.holders + self.plain


def role_counts(m: int) -> RoleCounts:
    """Giới hạn cứng: Sói = m/3, người có chức năng = m/3, Ma = m/9 (từ 12 người), còn lại là người thường.

    Làm tròn xuống: 5 người → 1 Sói, 1 người có chức năng, 3 người thường.
    """
    wolves = m // 3
    holders = m // 3
    ghosts = m // 9 if m >= THREE_FACTION_FROM else 0
    return RoleCounts(wolves, holders, ghosts, m - wolves - holders - ghosts)


def faction_counts(m: int) -> list[tuple[Faction, int]]:
    """Số người mỗi phe lúc bắt đầu (phe Người gồm cả người có chức năng và người thường)."""
    c = role_counts(m)
    return [(Faction.WOLF, c.wolves), (Faction.GHOST, c.ghosts), (Faction.VILLAGER, c.villagers)]


WOLF_KILL_SHARE = 0.25  # tỉ lệ Sói có Giết trực tiếp; còn lại Giết khi chết (chọn bằng mô phỏng cân bằng)
HOLDER_GROUP_WEIGHTS = (3, 3, 1, 1)  # trọng số nhóm: tấn công, phòng thủ, gây rối, tình báo (cho người có chức năng sau 4 người đầu)


# Chức năng không thể cấm khi chia ngẫu nhiên: người thường, Biến hình của Ma, và Giết trực tiếp (Sói cần ít nhất một người chủ động giết).
UNBANNABLE = frozenset({Ability.NONE, Ability.TRANSFORM, Ability.KILL})


def check_bans(banned: Iterable[Ability]) -> frozenset[Ability]:
    """Bộ chức năng bị cấm khi chia ngẫu nhiên, nếu hợp lệ: không cấm chức năng bắt buộc, và mỗi nhóm (tấn công, phòng thủ, gây rối, tình báo) còn ít nhất một."""
    banned = frozenset(banned)
    fixed = banned & UNBANNABLE
    if fixed:
        raise GameError("Không thể cấm: " + ", ".join(sorted(ability.value for ability in fixed)))
    for group in (OFFENSIVE, DEFENSIVE, DISRUPTIVE, INTEL):
        if all(ability in banned for ability in group):
            raise GameError("Không thể cấm hết một nhóm chức năng")
    return banned


def wolf_abilities(count: int, banned: frozenset[Ability] = frozenset()) -> list[Ability]:
    """Sói luôn có chức năng tấn công; đảm bảo ít nhất một Sói có Giết trực tiếp (chủ động)."""
    if count == 0:
        return []
    if Ability.KILL_ON_DEATH in banned:  # chỉ còn Giết trực tiếp
        return [Ability.KILL] * count
    kills = max(1, round(WOLF_KILL_SHARE * count))
    abilities = [Ability.KILL] * kills + [Ability.KILL_ON_DEATH] * (count - kills)
    random.shuffle(abilities)
    return abilities


def holder_abilities(count: int, banned: frozenset[Ability] = frozenset()) -> list[Ability]:
    """4 người có chức năng đầu tiên mỗi người một nhóm khác nhau (đủ tấn công/phòng thủ/gây rối/tình báo);
    từ người thứ 5 trở đi chọn nhóm theo trọng số HOLDER_GROUP_WEIGHTS."""
    groups = [[ability for ability in group if ability not in banned] for group in (OFFENSIVE, DEFENSIVE, DISRUPTIVE, INTEL)]
    rotation = groups[:]
    random.shuffle(rotation)
    abilities = []
    for i in range(count):
        group = rotation[i] if i < len(rotation) else random.choices(groups, weights=HOLDER_GROUP_WEIGHTS)[0]
        abilities.append(random.choice(group))
    return abilities


Role = tuple[Faction, Ability]


def suggest_roles(m: int, banned: Iterable[Ability] = ()) -> list[Role]:
    """Phe + chức năng ngẫu nhiên theo giới hạn cứng role_counts(m) (đã xáo); `banned` là các chức năng không được chia (xem check_bans)."""
    c = role_counts(m)
    banned = check_bans(banned)
    roles: list[Role] = [(Faction.WOLF, a) for a in wolf_abilities(c.wolves, banned)]
    roles += [(Faction.GHOST, Ability.TRANSFORM)] * c.ghosts
    roles += [(Faction.VILLAGER, a) for a in holder_abilities(c.holders, banned)]
    roles += [(Faction.VILLAGER, Ability.NONE)] * c.plain
    random.shuffle(roles)
    return roles


def validate_roles(roles: Sequence[Role]) -> None:
    """Kiểm tra bộ vai tự chỉnh: số người, mỗi phe cần có người, chức năng hợp lệ với phe."""
    if not MIN_PLAYERS <= len(roles) <= MAX_PLAYERS:
        raise GameError(f"Số người chơi phải từ {MIN_PLAYERS} đến {MAX_PLAYERS}")
    for faction, ability in roles:
        if ability not in ALLOWED_ABILITIES[faction]:
            raise GameError(f"\"{ability.value}\" không dành cho phe {faction.value}")
    factions = {f for f, _ in roles}
    if Faction.WOLF not in factions or Faction.VILLAGER not in factions:
        raise GameError("Cần ít nhất 1 Sói và 1 Người")
