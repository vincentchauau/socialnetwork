"""Ma Sói tổng quát — game engine thuần logic (không print/input).

Luồng: SETUP -> NIGHT -> SETTLE -> DAY -> SETTLE -> NIGHT ...
SETTLE xử lý hàng đợi "giết khi chết"; nếu người chết là người thật thì dừng ở
REVENGE chờ họ chọn mục tiêu. Bot tự hành động ngay khi phase bắt đầu.
Định nghĩa vai nằm ở roles.py (re-export ở đây để mã cũ vẫn `from engine import ...`).
"""
from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from api.werewolf.engine import bots
from api.werewolf.engine.chat import Chat, ChatError, ChatMessage
from api.werewolf.engine.events import NightEvent, draw_event
from api.werewolf.engine.roles import (  # noqa: F401  (re-export)
    _DEFENSIVE,
    _DISRUPTIVE,
    _INTEL,
    _OFFENSIVE,
    _PASSIVE,
    ALLOWED_ABILITIES,
    DEFAULT_ABILITIES,
    HOLDER_GROUP_WEIGHTS,
    MAX_PLAYERS,
    MIN_PLAYERS,
    THREE_FACTION_FROM,
    WOLF_KILL_SHARE,
    Ability,
    Faction,
    GameError,
    Role,
    RoleCounts,
    faction_counts,
    role_counts,
    suggest_roles,
    validate_roles,
)

CHAT_SNAPSHOT = 120  # số tin chat tối đa trong mỗi bản state
MIN_TIMER = 5
MAX_TIMER = 600


class Phase(Enum):
    SETUP = "setup"
    NIGHT = "night"
    REVENGE = "revenge"
    DAY = "day"
    SETTLE = "settle"
    OVER = "over"


@dataclass
class Player:
    id: int
    name: str
    faction: Faction
    ability: Ability
    is_bot: bool = False
    alive: bool = True
    died_on: int | None = None  # đêm (số thứ tự) khi chết; None nếu còn sống


@dataclass(frozen=True)
class Event:
    seq: int
    round: str
    text: str
    audience: frozenset[int] | None  # None = công khai
    full_text: str | None = None  # bản có tên cho người xem nhật ký đầy đủ ('' = ẩn)


def _fac(f: Faction) -> dict[str, str]:
    return {"code": f.name, "label": f.value}


def _abi(a: Ability) -> dict[str, str]:
    return {"code": a.name, "label": a.value}


class Game:
    def __init__(self, entries: Sequence[tuple[str, bool]],
                 roles: Sequence[Role] | None = None, events: bool = False, timer: int | None = None,
                 dead_talk: bool = True, clock: Callable[[], float] = time.monotonic) -> None:
        m = len(entries)
        if m < MIN_PLAYERS:
            raise GameError(f"Cần ít nhất {MIN_PLAYERS} người chơi")
        if timer is not None and not MIN_TIMER <= timer <= MAX_TIMER:
            raise GameError(f"Đồng hồ phải từ {MIN_TIMER} đến {MAX_TIMER} giây")
        if roles is not None:
            if len(roles) != m:
                raise GameError("Số vai không khớp số người chơi")
            validate_roles(roles)
        self.m = m
        self._clock = clock  # đồng hồ có thể thay thế khi test
        self._round = ""
        self.max_nights = m * 3
        self.phase = Phase.SETUP
        self.night = 0
        self.game_over = False
        self.winner: Faction | None = None
        self.events: list[Event] = []
        self.public_info: dict[int, dict[str, Any]] = {}  # ai cũng biết
        self.wolf_info: dict[int, dict[str, Any]] = {}  # chỉ phe Sói biết
        self.last_protect_target: dict[int, int] = {}

        self.actions: dict[int, int] = {}  # đêm: pid -> target id
        self.night_options: dict[int, list[int]] = {}
        self.wolf_actions: dict[int, int] = {}  # đêm: Sói -> mục tiêu vote giết (0 = bỏ phiếu trắng)
        self.wolf_options: dict[int, list[int]] = {}
        self.votes: dict[int, int] = {}  # ngày: pid -> target id (0 = bỏ trắng)
        self.skipped: set[int] = set()
        self.pending_revenge: int | None = None
        self.revenge_options: list[int] = []
        self._revenge_queue: list[Player] = []
        self._next = "day"
        self._last_step = "night"  # bước vừa xử lý xong: "night" hoặc "day" (để biết thẻ tóm tắt là Bình minh hay Hoàng hôn)

        self.dead_talk = dead_talk  # True: người chết chat chung với người sống; False: kênh riêng của người chết
        self.events_enabled = events  # bật thẻ sự kiện ngẫu nhiên mỗi đêm
        self.forced_event: NightEvent | None = None  # (dùng khi test) luôn dùng thẻ này
        self.event: NightEvent | None = None
        self.vote_history: list[dict[int, int]] = []  # phiếu treo cổ của từng ngày đã qua (bot dùng để nghi ngờ)
        self.chat = Chat()
        self.timer = timer  # giây cho mỗi lượt đêm; ban ngày gấp đôi; None = không giới hạn
        self._timer_key: tuple[Any, ...] | None = None
        self._timer_start = 0.0
        self.recap: dict[str, Any] | None = None  # thẻ tóm tắt Bình minh / Hoàng hôn gần nhất
        self._recap_seq = 0
        self._deaths: list[dict[str, Any]] = []
        self._wolf_target_for = -1
        self._wolf_target_id = 0

        roles = list(roles) if roles is not None else suggest_roles(m)
        self.players = [
            Player(i + 1, name, f, a, is_bot)
            for i, ((f, a), (name, is_bot)) in enumerate(zip(roles, entries))
        ]
        # Sói biết đồng bọn ngay từ đầu (cần để phối hợp Vote chết).
        self.wolf_info = {p.id: {"faction": Faction.WOLF}
                          for p in self.players if p.faction == Faction.WOLF}

    # ---------- truy vấn ----------
    def player(self, pid: int) -> Player:
        p = next((x for x in self.players if x.id == pid), None)
        if p is None:
            raise GameError("Người chơi không tồn tại")
        return p

    def alive(self, faction: Faction | None = None) -> list[Player]:
        return [p for p in self.players if p.alive and (faction is None or p.faction == faction)]

    def _knowledge_for(self, p: Player) -> dict[int, dict[str, Any]]:
        merged = {pid: dict(info) for pid, info in self.public_info.items()}
        if p.faction == Faction.WOLF:
            for pid, info in self.wolf_info.items():
                merged.setdefault(pid, {}).update(info)
        return merged

    def check_win(self) -> bool:
        w, v, g = (len(self.alive(f)) for f in (Faction.WOLF, Faction.VILLAGER, Faction.GHOST))
        t = w + v + g
        if t == 0:  # không còn ai sống: hòa (không có phe thắng)
            self.game_over, self.winner = True, None
            return True
        winners: list[tuple[Faction, int]] = []
        if w == 0 and t > 0:
            winners.append((Faction.VILLAGER, v))
        if w > 0 and w >= v:
            winners.append((Faction.WOLF, w))
        if g > 0 and g * 2 >= t:
            winners.append((Faction.GHOST, g))
        if len(winners) == 1:
            self.game_over, self.winner = True, winners[0][0]
        elif len(winners) > 1:
            winners.sort(key=lambda x: x[1], reverse=True)
            if winners[0][1] > winners[1][1]:
                self.game_over, self.winner = True, winners[0][0]
        return self.game_over

    # ---------- nhật ký ----------
    def _add_event(self, text: str, audience: frozenset[int] | None,
                   full_text: str | None = None) -> None:
        self.events.append(Event(len(self.events), self._round, text, audience, full_text))

    def _announce(self, text: str) -> None:
        self._add_event(text, None)

    def _note(self, players: Sequence[Player], text: str, full_text: str | None = None) -> None:
        self._add_event(text, frozenset(p.id for p in players), full_text)

    def _share(self, seer: Player, target: Player, key: str, value: Any, text: str) -> None:
        """Kết quả soi: phe Sói giữ riêng cho Sói, phe khác thì công khai."""
        if seer.faction == Faction.WOLF:
            self.wolf_info.setdefault(target.id, {})[key] = value
            wolves = [x for x in self.players if x.faction == Faction.WOLF]
            self._note(wolves, f"🔮 {text}", f"🔮 (kết quả riêng của Sói) {text}")
        else:
            self.public_info.setdefault(target.id, {})[key] = value
            self._announce(f"📢 {text}")

    # ---------- điều khiển ----------
    def start(self) -> None:
        if self.phase != Phase.SETUP:
            raise GameError("Game đã bắt đầu")
        self._start_night()
        self._advance()

    def submit(self, pid: int, target: int, kind: str = "ability") -> None:
        """`kind`: "ability" (chức năng) hoặc "wolf" (vote giết của Sói, target 0 = bỏ phiếu trắng)."""
        p = self.player(pid)
        if self.phase == Phase.NIGHT:
            if kind not in ("ability", "wolf"):
                raise GameError("Loại hành động không hợp lệ")
            store, options = ((self.wolf_actions, self.wolf_options) if kind == "wolf"
                              else (self.actions, self.night_options))
            base = options.get(pid)
            if base is None:
                raise GameError("Bạn không có hành động này đêm nay")
            if pid in store or pid in self.skipped:
                raise GameError("Bạn đã chọn rồi")
            opts = self._exclusive(pid, kind, base)
            if target in base and target not in opts:
                raise GameError("Người này đã bị Giết trực tiếp (hoặc vote giết) rồi, hãy chọn người khác")
            if target not in opts and not (kind == "wolf" and target == 0):
                raise GameError("Mục tiêu không hợp lệ")
            store[pid] = target
            if kind == "ability" and pid in self.wolf_options and pid not in self.wolf_actions \
                    and not self._exclusive(pid, "wolf", self.wolf_options[pid]):
                self.wolf_actions[pid] = 0  # không còn ai khác để vote giết: tự bỏ phiếu trắng
        elif self.phase == Phase.DAY:
            if not p.alive:
                raise GameError("Người chết không được vote")
            if pid in self.votes or pid in self.skipped:
                raise GameError("Bạn đã vote rồi")
            valid = {x.id for x in self.alive() if x.id != pid}
            if target != 0 and target not in valid:
                raise GameError("Mục tiêu không hợp lệ")
            self.votes[pid] = target
        elif self.phase == Phase.REVENGE:
            if pid != self.pending_revenge:
                raise GameError("Chưa đến lượt bạn")
            if target not in self.revenge_options:
                raise GameError("Mục tiêu không hợp lệ")
            t = self.player(target)
            self._announce(f"🏹 {p.name} kéo theo → {t.name}")
            self._kill(t, "bị kéo theo")
            self.pending_revenge = None
            self.phase = Phase.SETTLE
        else:
            raise GameError("Hiện không thể thực hiện hành động")
        self._advance()

    def force(self) -> None:
        """Host ép qua phase: người chưa chọn coi như bỏ qua."""
        if self.phase in (Phase.SETUP, Phase.OVER):
            raise GameError("Không có phase nào để bỏ qua")
        self.skipped.update(self._missing())
        if self.phase == Phase.REVENGE:
            self.pending_revenge = None
            self.phase = Phase.SETTLE
        self._advance()

    def take_over(self, pid: int) -> None:
        """Người chơi rời ván: ghế chuyển cho bot (lượt đang chờ coi như bỏ qua, các lượt sau bot tự chơi)."""
        p = self.player(pid)
        if p.is_bot:
            return
        p.is_bot = True
        if self.phase in (Phase.SETUP, Phase.OVER):
            return
        if pid in self._missing():
            self.skipped.add(pid)
        if self.phase == Phase.REVENGE and self.pending_revenge == pid:
            self.pending_revenge = None
            self.phase = Phase.SETTLE
        self._advance()

    # ---------- đồng hồ ----------
    def _timer_budget(self) -> int | None:
        if not self.timer or self.phase not in (Phase.NIGHT, Phase.DAY, Phase.REVENGE):
            return None
        return self.timer * (2 if self.phase == Phase.DAY else 1)

    def seconds_left(self, now: float | None = None) -> float | None:
        """Số giây còn lại của lượt hiện tại (None nếu không giới hạn). Đồng hồ bắt đầu khi lượt được quan sát lần đầu."""
        budget = self._timer_budget()
        if budget is None:
            return None
        now = self._clock() if now is None else now
        key = (self.phase, self.night, self.pending_revenge)
        if key != self._timer_key:
            self._timer_key, self._timer_start = key, now
        return max(0.0, budget - (now - self._timer_start))

    def tick(self, now: float | None = None) -> bool:
        """Hết giờ thì ép qua lượt (người chưa chọn bị bỏ qua). Trả về True nếu game vừa tiến lên."""
        left = self.seconds_left(now)
        if left is None or left > 0:
            return False
        self.force()
        return True

    # ---------- chat ----------
    def chat_channel_for(self, p: Player) -> str | None:
        """Kênh `p` đang được gửi tin: công khai ban ngày, Sói ban đêm, người chết luôn có kênh riêng."""
        if self.game_over:
            return "public"
        if not p.alive:
            return "public" if self.dead_talk else "dead"
        if self.phase == Phase.DAY:
            return "public"
        if self.phase == Phase.NIGHT and p.faction == Faction.WOLF:
            return "wolf"
        return None

    def post_chat(self, pid: int, text: str, target: int = 0, now: float | None = None) -> ChatMessage:
        p = self.player(pid)
        channel = self.chat_channel_for(p)
        if channel is None:
            raise GameError("Hiện chưa thể chat")
        if target and all(x.id != target for x in self.players):
            raise GameError("Người được nhắc tới không tồn tại")
        try:
            return self.chat.add(pid, channel, text, self._round or "Chuẩn bị", target,
                          self._clock() if now is None else now, dead=not p.alive)
        except ChatError as e:
            raise GameError(str(e)) from e

    def message_visible(self, viewer: Player, m: ChatMessage, everything: bool = False) -> bool:
        """Tin chat `m` có hiển thị cho `viewer` không (kênh công khai / Sói / người chết)."""
        return (everything or m.channel == "public"
                or (m.channel == "wolf" and viewer.faction == Faction.WOLF)
                or (m.channel == "dead" and not viewer.alive))

    def chat_entry(self, m: ChatMessage) -> dict[str, Any]:
        names = {x.id: x.name for x in self.players}
        return {"seq": m.seq, "round": m.round, "channel": m.channel, "text": m.text, "target": m.target,
                "dead": m.dead, "author": {"id": m.author, "name": names.get(m.author, "?")}}

    def _visible_chat(self, viewer: Player, everything: bool) -> list[dict[str, Any]]:
        return [self.chat_entry(m) for m in self.chat.messages[-CHAT_SNAPSHOT:]
                if self.message_visible(viewer, m, everything)]

    def _missing(self) -> list[int]:
        if self.phase == Phase.NIGHT:
            pending = [i for i in sorted(set(self.night_options) | set(self.wolf_options))
                       if (i in self.night_options and i not in self.actions)
                       or (i in self.wolf_options and i not in self.wolf_actions)]
            return [i for i in pending if i not in self.skipped]
        elif self.phase == Phase.DAY:
            ids, done = [p.id for p in self.alive()], set(self.votes)
        elif self.phase == Phase.REVENGE and self.pending_revenge is not None:
            ids, done = [self.pending_revenge], set()
        else:
            return []
        return [i for i in ids if i not in done and i not in self.skipped]

    def _advance(self) -> None:
        """Chạy các chuyển phase tự động cho tới khi cần người thật nhập."""
        while True:
            if self.phase == Phase.NIGHT:
                if self._missing():
                    return
                self._resolve_night()
            elif self.phase == Phase.DAY:
                if self._missing():
                    return
                self._resolve_day()
            elif self.phase == Phase.SETTLE:
                if not self._settle():
                    return
            else:
                return

    # ---------- chết / kết thúc ----------
    def _kill(self, p: Player, cause: str) -> None:
        if not p.alive:
            return
        p.alive = False
        p.died_on = self.night
        death: dict[str, Any] = {"id": p.id, "name": p.name, "cause": cause}
        self._deaths.append(death)
        self._announce(f"💀 {p.name} chết [{cause}]")
        if p.ability == Ability.REVEAL_ON_DEATH:
            death["revealed"] = {"faction": _fac(p.faction), "ability": _abi(p.ability)}
            self.public_info.setdefault(p.id, {}).update(faction=p.faction, ability=p.ability)
            self._announce(f"📢 Lộ: {p.name} = {p.faction.value}, {p.ability.value}")
        if p.ability == Ability.KILL_ON_DEATH:
            self._revenge_queue.append(p)

    def _check_end(self) -> bool:
        if not self.check_win():
            return False
        self._end_game()
        return True

    def _flush_recap(self, kind: str, round_no: int) -> None:
        """Gói những ai chết ở bước vừa rồi thành thẻ Bình minh (sau đêm) hoặc Hoàng hôn (sau ngày)."""
        self._recap_seq += 1
        self.recap = {"seq": self._recap_seq, "kind": kind, "round": round_no, "deaths": self._deaths}
        self._deaths = []

    def _end_game(self) -> None:
        if self._deaths:
            self._flush_recap("dawn" if self._last_step == "night" else "dusk", self.night)
        self.game_over = True
        self.phase = Phase.OVER
        if self.winner is None:
            self._announce("🤝 HÒA — không còn ai sống!")
        else:
            self._announce(f"🏆 PHE {self.winner.value.upper()} THẮNG!")

    def _settle(self) -> bool:
        """Xử lý hàng đợi giết-khi-chết. False nếu đang chờ người thật chọn."""
        while self._revenge_queue:
            p = self._revenge_queue.pop(0)
            enemies = [x for x in self.alive() if x.faction != p.faction]
            if not enemies:
                continue
            if p.is_bot:
                know = self._knowledge_for(p)
                known = [x for x in enemies
                         if know.get(x.id, {}).get("faction") not in (None, p.faction)]
                t = random.choice(known or enemies)
                self._announce(f"🏹 {p.name} kéo theo → {t.name}")
                self._kill(t, "bị kéo theo")
            else:
                self.phase = Phase.REVENGE
                self.pending_revenge = p.id
                self.revenge_options = [x.id for x in enemies]
                self.skipped = set()
                return False
        if self._check_end():
            return True
        if self._next == "day":
            self._start_day()
        elif self.night >= self.max_nights:
            counts = {f: len(self.alive(f)) for f in Faction}
            self.winner = max(counts, key=lambda f: counts[f])
            self._end_game()
        else:
            self._start_night()
        return True

    # ---------- ĐÊM ----------
    def _options_for(self, p: Player) -> list[int]:
        if p.ability in _PASSIVE:
            return []
        if p.ability == Ability.TRANSFORM and p.faction != Faction.GHOST:
            return []
        ids = [x.id for x in self.alive() if x.id != p.id]
        if p.ability == Ability.BLOCK_EFFECTS:  # không bảo vệ cùng người 2 đêm liền
            ids = [i for i in ids if i != self.last_protect_target.get(p.id)]
        return ids

    def _exclusive(self, pid: int, kind: str, ids: list[int]) -> list[int]:
        """Sói có Giết trực tiếp: người đã chọn ở hành động này bị loại khỏi hành động kia (đòn thứ hai là thừa)."""
        p = self.player(pid)
        if p.faction != Faction.WOLF or p.ability != Ability.KILL:
            return ids
        other = self.actions.get(pid) if kind == "wolf" else self.wolf_actions.get(pid)
        return [i for i in ids if i != other] if other else ids

    def _wolf_options_for(self, p: Player) -> list[int]:
        """Mọi Sói còn sống đều có vote giết ban đêm mặc định; mục tiêu là người không phải Sói."""
        if p.faction != Faction.WOLF:
            return []
        return [x.id for x in self.alive() if x.faction != Faction.WOLF]

    def _start_night(self) -> None:
        self.night += 1
        self.phase = Phase.NIGHT
        self._round = f"Đêm {self.night}"
        if self.night > 1:
            self._flush_recap("dusk", self.night - 1)
        self.event = self.forced_event or (draw_event() if self.events_enabled else None)
        if self.event:
            self._announce(f"🎴 Sự kiện: {self.event.icon} {self.event.title} — {self.event.text}")
        self.actions, self.wolf_actions, self.skipped = {}, {}, set()
        self.night_options, self.wolf_options = {}, {}
        for p in self.alive():
            opts = self._options_for(p)
            if opts:
                self.night_options[p.id] = opts
                if p.is_bot:
                    self.actions[p.id] = self._auto_target(p, [self.player(i) for i in opts]).id
            wolf_opts = self._wolf_options_for(p)
            if p.ability == Ability.KILL and len(wolf_opts) == 1 and wolf_opts[0] in opts:
                # Chỉ còn một mục tiêu và Giết trực tiếp đã nhắm tới được: vote giết cùng người đó là thừa.
                wolf_opts = []
            if wolf_opts:
                self.wolf_options[p.id] = wolf_opts
                if p.is_bot:
                    choices = self._exclusive(p.id, "wolf", wolf_opts)
                    self.wolf_actions[p.id] = (
                        self._auto_wolf_target(p, [self.player(i) for i in choices]).id if choices else 0)

    def _resolve_night(self) -> None:
        self._last_step = "night"
        ev = self.event.code if self.event else None
        alive_before = len(self.alive())
        acts = {pid: (self.player(pid), self.player(tid)) for pid, tid in self.actions.items()}
        for p, t in acts.values():  # người dùng thấy bản "Bạn…"; nhật ký đầy đủ thấy bản có tên
            self._add_event(f"📝 Bạn dùng {p.ability.value} lên {t.name}", frozenset({p.id}),
                            f"📝 {p.name} ({p.faction.value}, {p.ability.value}) → {t.name}")
        wolf_acts = {pid: (self.player(pid), self.player(tid))
                     for pid, tid in self.wolf_actions.items() if tid}  # tid 0 = bỏ phiếu trắng
        for p, t in wolf_acts.values():
            self._add_event(f"📝 Bạn vote Sói lên {t.name}", frozenset({p.id}),
                            f"📝 {p.name} (Sói) vote Sói → {t.name}")
        blocked: set[int] = set()
        protected: set[int] = set()
        reflected: set[int] = set()

        def of(ability: Ability):
            # Generator: kiểm tra `blocked` tại thời điểm duyệt, như bản gốc.
            for pid, (p, t) in list(acts.items()):
                if p.ability == ability and pid not in blocked:
                    yield pid, p, t

        for pid, p, t in of(Ability.BLOCK_ABILITY):
            blocked.add(t.id)
            self._note([p], f"🚫 Bạn khóa chức năng {t.name}", f"🚫 {p.name} khóa chức năng {t.name}")
            self._note([t], "🚫 Chức năng của bạn bị khóa đêm nay", "")

        for pid, p, t in of(Ability.REVERSE_ABILITY):
            if (t.id in acts or t.id in wolf_acts) and t.id not in blocked:
                self._note([p], f"🔄 Bạn đảo chức năng của {t.name}",
                           f"🔄 {p.name} đảo chức năng của {t.name} (hành động của {t.name} quay về chính họ)")
                for book in (acts, wolf_acts):  # cả chức năng lẫn vote Sói của mục tiêu
                    if t.id in book:
                        old_p, _ = book[t.id]
                        book[t.id] = (old_p, old_p)

        for pid, p, t in of(Ability.BLOCK_EFFECTS):
            protected.add(t.id)
            self._note([p], f"🛡 Bạn bảo vệ {t.name}", f"🛡 {p.name} bảo vệ {t.name}")
            self.last_protect_target[pid] = t.id

        for pid, p, t in of(Ability.REVERSE_EFFECTS):
            reflected.add(t.id)
            self._note([p], f"↩️ Bạn đặt phản đòn lên {t.name}", f"↩️ {p.name} đặt phản đòn lên {t.name}")

        if ev == "FULL_MOON":  # Trăng tròn: bảo vệ và phản đòn mất tác dụng
            protected.clear()
            reflected.clear()

        for pid, p, t in of(Ability.SEE_FACTION):
            if ev == "FOG":
                self._note([p], "🌫️ Sương mù che mắt bạn, không thấy gì", "")
            else:
                self._share(p, t, "faction", t.faction, f"{t.name} thuộc nhóm {t.faction.value}")
        for pid, p, t in of(Ability.SEE_ABILITY):
            if ev == "FOG":
                self._note([p], "🌫️ Sương mù che mắt bạn, không thấy gì", "")
            else:
                self._share(p, t, "ability", t.ability, f"{t.name} có chức năng {t.ability.value}")

        for pid, p, t in of(Ability.TRANSFORM):
            if t.faction == Faction.GHOST:
                self._note([p], f"👻 Biến hình {t.name} thất bại (đã là Ma)",
                           f"👻 {p.name} biến hình {t.name} thất bại (đã là Ma)")
            elif t.id in protected and ev != "GHOST_NIGHT":
                self._note([p], f"👻 Biến hình {t.name} thất bại (được bảo vệ)",
                           f"👻 {p.name} biến hình {t.name} thất bại (được bảo vệ)")
            elif t.id in reflected and ev != "GHOST_NIGHT":
                self._note([p], f"👻 Biến hình {t.name} thất bại (phản đòn)",
                           f"👻 {p.name} biến hình {t.name} thất bại (phản đòn)")
            else:
                t.faction = Faction.GHOST
                self._note([p], f"👻 {t.name} đã bị biến thành Ma",
                           f"👻 {p.name} biến {t.name} thành Ma")
                self._note([t], "👻 Bạn đã bị biến thành Ma! Giờ bạn thuộc phe Ma.", "")
                if self._check_end():
                    return

        kill_targets: list[Player] = []
        for pid, p, t in of(Ability.KILL):
            if t.id in protected:
                self._note([p], f"⚔️ Giết {t.name} thất bại (được bảo vệ)",
                           f"⚔️ {p.name} giết {t.name} thất bại (được bảo vệ)")
            elif t.id in reflected:
                self._note([p], f"⚔️ Giết {t.name} bị phản đòn — bạn chết thay",
                           f"⚔️ {p.name} giết {t.name} bị phản đòn — {p.name} chết thay")
                kill_targets.append(p)
            else:
                kill_targets.append(t)

        wolves = [x for x in self.players if x.faction == Faction.WOLF]
        wolf_votes: dict[int, int] = {}
        if ev == "PEACEFUL" and wolf_acts:
            self._note(wolves, "🕊️ Đêm bình yên: vote giết của Sói không có hiệu lực")
        for pid, (p, t) in ({} if ev == "PEACEFUL" else wolf_acts).items():
            if pid in blocked or p.faction != Faction.WOLF:
                continue
            if t.id in protected:
                self._note(wolves, f"🐺 Vote của {p.name} vào {t.name} bị chặn (được bảo vệ)")
                continue
            target_id = p.id if t.id in reflected else t.id
            if target_id == p.id:
                self._note(wolves, f"🐺 Vote của {p.name} vào {t.name} bị phản đòn, phiếu quay về {p.name}")
            wolf_votes[target_id] = wolf_votes.get(target_id, 0) + 1
        if wolf_votes:
            ranked = sorted(wolf_votes.items(), key=lambda kv: -kv[1])
            tally = ", ".join(f"{self.player(tid).name} {v}" for tid, v in ranked)
            top_votes = ranked[0][1]
            top = [tid for tid, v in ranked if v == top_votes]
            if len(top) == 1:
                victim = self.player(top[0])
                kill_targets.append(victim)
                self._note(wolves, f"🐺 Sói vote ({tally}) → giết {victim.name}")
            elif ev == "BLOOD_MOON":
                victim = self.player(random.choice(top))
                kill_targets.append(victim)
                self._note(wolves, f"🩸 Trăng máu: Sói vote hòa ({tally}), ngẫu nhiên chọn giết {victim.name}")
            else:
                self._note(wolves, f"🐺 Sói vote ({tally}) → hòa phiếu, vote Sói không giết ai")

        seen: set[int] = set()
        for t in kill_targets:
            if t.id not in seen:
                seen.add(t.id)
                self._kill(t, "bị giết ban đêm")
        if len(self.alive()) == alive_before:
            self._announce("🌅 Đêm qua yên bình, không ai chết.")
        self.phase = Phase.SETTLE
        self._next = "day"

    def _auto_target(self, p: Player, others: list[Player]) -> Player:
        know = self._knowledge_for(p)
        known_enemies = [x for x in others
                         if know.get(x.id, {}).get("faction") not in (None, p.faction)]
        allies = [x for x in others if x.faction == p.faction]
        if p.ability == Ability.KILL:
            enemies = [x for x in others if x.faction != p.faction]
            return random.choice(known_enemies or enemies or others)
        if p.ability == Ability.TRANSFORM:
            non_ghost = [x for x in others if x.faction != Faction.GHOST]
            unknown = [x for x in non_ghost if x.id not in know]
            return random.choice(unknown or non_ghost or others)
        if p.ability in (Ability.BLOCK_EFFECTS, Ability.REVERSE_EFFECTS):
            return random.choice(allies or others)
        if p.ability in (Ability.BLOCK_ABILITY, Ability.REVERSE_ABILITY):
            return random.choice(known_enemies or others)
        if p.ability in (Ability.SEE_FACTION, Ability.SEE_ABILITY):
            unknown = [x for x in others if x.id not in know]
            return random.choice(unknown or others)
        return random.choice(others)

    def _auto_wolf_target(self, p: Player, others: list[Player]) -> Player:
        know = self._knowledge_for(p)
        known_enemies = [x for x in others
                         if know.get(x.id, {}).get("faction") not in (None, p.faction)]
        enemies = [x for x in others if x.faction != p.faction]
        return random.choice(known_enemies or enemies or others)

    # ---------- NGÀY ----------
    def _start_day(self) -> None:
        self.phase = Phase.DAY
        self._round = f"Ngày {self.night}"
        self._flush_recap("dawn", self.night)
        self.votes, self.skipped = {}, set()
        for line_bot, text, target in bots.chatter(self):  # bot lên tiếng trước khi vote
            self.chat.add(line_bot.id, "public", text, self._round, target, throttle=False)
        cast: dict[int, int] = {}
        day_bots = [p for p in self.alive() if p.is_bot]
        random.shuffle(day_bots)  # thứ tự ngẫu nhiên để việc "theo phe đang dẫn đầu" không thiên vị ai
        for p in day_bots:
            pick = bots.day_vote(self, p, [x for x in self.alive() if x != p], cast)
            self.votes[p.id] = cast[p.id] = pick.id

    def _resolve_day(self) -> None:
        self._last_step = "day"
        self.vote_history.append(dict(self.votes))
        for voter_id, target in self.votes.items():
            voter = self.player(voter_id)
            who = self.player(target).name if target else "bỏ trắng"
            self._add_event(f"🗳 {voter.name} vote → {who}", None,
                            f"🗳 {voter.name} ({voter.faction.value}) vote → {who}")
        tally: dict[int, int] = {}
        for target in self.votes.values():
            if target:
                tally[target] = tally.get(target, 0) + 1
        self._next = "night"
        self.phase = Phase.SETTLE
        if not tally:
            self._announce("⚖️ Không ai bị treo cổ.")
            return
        top_votes = max(tally.values())
        top = [tid for tid, v in tally.items() if v == top_votes]
        if len(top) > 1 and self.event is not None and self.event.code == "JUSTICE":
            pick = self.player(random.choice(top))
            self._announce(f"⚖️ Ngày công lý: hòa phiếu nên ngẫu nhiên chọn {pick.name}")
            top = [pick.id]
        if len(top) > 1:
            self._announce("⚖️ Hòa phiếu — không ai bị treo cổ.")
            return
        victim = self.player(top[0])
        self._announce(f"📊 {victim.name} bị treo cổ ({top_votes} phiếu)")
        self._kill(victim, "bị treo cổ")

    # ---------- view cho client ----------
    def can_see_everything(self, pid: int) -> bool:
        """Chỉ người đã chết hoặc khi ván đã kết thúc mới được xem nhật ký đầy đủ / góc nhìn người khác.

        (Khác bản gốc, nơi ai cũng xem được: trên nền tảng này điều đó lộ bí mật giữa người thật.)
        """
        return self.game_over or not self.player(pid).alive

    def view_for(self, pid: int, perspective: bool = False) -> dict[str, Any]:
        """Góc nhìn của người chơi `pid`. `perspective=True`: đúng những gì người đó biết (không xem toàn bộ).

        Người còn sống chỉ thấy nhật ký của mình; người chết (và mọi người khi ván xong) thấy nhật ký đầy đủ.
        """
        me = self.player(pid)
        known = self._knowledge_for(me)
        reveal = self.game_over and not perspective
        see_all = self.can_see_everything(pid) and not perspective
        players = []
        for p in self.players:
            info = known.get(p.id, {})
            full = reveal or p.id == pid
            faction = p.faction if full else info.get("faction")
            ability = p.ability if full else info.get("ability")
            players.append({
                "id": p.id, "name": p.name, "alive": p.alive, "isBot": p.is_bot,
                "faction": _fac(faction) if faction else None,
                "ability": _abi(ability) if ability else None,
            })
        log = []
        for e in self.events:
            if e.audience is not None and pid in e.audience:
                text = e.text
            elif see_all:
                text = e.text if e.full_text is None else e.full_text
            elif e.audience is None:
                text = e.text
            else:
                continue
            if text:
                log.append({"round": e.round, "text": text})
        return {
            "phase": self.phase.value,
            "night": self.night,
            "gameOver": self.game_over,
            "winner": _fac(self.winner) if self.winner else None,
            "me": {"id": me.id, "name": me.name, "alive": me.alive,
                   "faction": _fac(me.faction), "ability": _abi(me.ability)},
            "players": players,
            "actions": self._actions_for(me),
            "waitingFor": len(self._missing()),
            "log": log,
            "event": self.event.view() if self.event and (self.phase == Phase.NIGHT or self.event.affects_day) else None,
            "recap": self.recap,
            "timer": self._timer_view(),
            "chat": self._visible_chat(me, everything=reveal),
            "chatChannel": self.chat_channel_for(me),
        }

    def _timer_view(self) -> dict[str, Any] | None:
        left = self.seconds_left()
        if left is None:
            return None
        return {"total": self._timer_budget(), "secondsLeft": round(left, 1)}

    def _actions_for(self, me: Player) -> list[dict[str, Any]]:
        """Các hành động người chơi đang phải/được làm: night (chức năng), wolf (vote Sói), day, revenge."""
        def entry(kind: str, ids: list[int], store: dict[int, int], can_abstain: bool) -> dict[str, Any]:
            return {"kind": kind, "options": ids, "submitted": me.id in store,
                    "current": store.get(me.id), "canAbstain": can_abstain}

        out: list[dict[str, Any]] = []
        if self.phase == Phase.NIGHT:
            if me.id in self.night_options:
                out.append(entry("night", self._exclusive(me.id, "ability", self.night_options[me.id]),
                                 self.actions, False))
            if me.id in self.wolf_options:
                out.append(entry("wolf", self._exclusive(me.id, "wolf", self.wolf_options[me.id]),
                                 self.wolf_actions, True))
        elif self.phase == Phase.DAY and me.alive:
            ids = [x.id for x in self.alive() if x.id != me.id]
            out.append(entry("day", ids, self.votes, True))
        elif self.phase == Phase.REVENGE and self.pending_revenge == me.id:
            out.append(entry("revenge", self.revenge_options, {}, False))
        return out
