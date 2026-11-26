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
    DEFENSIVE,
    DISRUPTIVE,
    INTEL,
    OFFENSIVE,
    PASSIVE,
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

import logging
logger = logging.getLogger(__name__)

CHAT_SNAPSHOT = 120  # maximum chat messages in each state snapshot
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
    died_on: int | None = None  # the night (number) of death; None if still alive


@dataclass(frozen=True)
class Event:
    seq: int
    round: str
    text: str
    audience: frozenset[int] | None  # None = public
    full_text: str | None = None  # the version with names for viewers of the full log ('' = hidden)


def fac(f: Faction) -> dict[str, str]:
    try:
        return {"code": f.name, "label": f.value}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("fac failed")
        raise


def abi(a: Ability) -> dict[str, str]:
    try:
        return {"code": a.name, "label": a.value}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("abi failed")
        raise


class Game:
    def __init__(self, entries: Sequence[tuple[str, bool]],
                 roles: Sequence[Role] | None = None, events: bool = False, timer: int | None = None,
                 dead_talk: bool = True, clock: Callable[[], float] = time.monotonic) -> None:
        try:
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
            self._clock = clock  # a clock that can be replaced in tests
            self._round = ""
            self.max_nights = m * 3
            self.phase = Phase.SETUP
            self.night = 0
            self.game_over = False
            self.winner: Faction | None = None
            self.events: list[Event] = []
            self.public_info: dict[int, dict[str, Any]] = {}  # known to everyone
            self.wolf_info: dict[int, dict[str, Any]] = {}  # known only to the wolves
            self.last_protect_target: dict[int, int] = {}

            self.actions: dict[int, int] = {}  # night: pid -> target id
            self.night_options: dict[int, list[int]] = {}
            self.wolf_actions: dict[int, int] = {}  # night: wolf -> kill-vote target (0 = blank vote)
            self.wolf_options: dict[int, list[int]] = {}
            self.votes: dict[int, int] = {}  # day: pid -> target id (0 = blank)
            self.skipped: set[int] = set()
            self.pending_revenge: int | None = None
            self.revenge_options: list[int] = []
            self._revenge_queue: list[Player] = []
            self._next = "day"
            self._last_step = "night"  # the step just finished: "night" or "day" (to know whether the recap is Dawn or Dusk)

            self.dead_talk = dead_talk  # True: the dead chat in the shared channel with the living; False: the dead have their own channel
            self.events_enabled = events  # turn on random event cards each night
            self.forced_event: NightEvent | None = None  # (for tests) always use this card
            self.event: NightEvent | None = None
            self.vote_history: list[dict[int, int]] = []  # the lynch votes of each past day (bots use them to suspect)
            self.chat = Chat()
            self.timer = timer  # seconds for each night turn; daytime is double; None = no limit
            self._timer_key: tuple[Any, ...] | None = None
            self._timer_start = 0.0
            self.recap: dict[str, Any] | None = None  # the latest Dawn / Dusk recap card
            self._recap_seq = 0
            self._deaths: list[dict[str, Any]] = []
            self._wolf_target_for = -1
            self._wolf_target_id = 0

            roles = list(roles) if roles is not None else suggest_roles(m)
            self.players = [
                Player(i + 1, name, f, a, is_bot)
                for i, ((f, a), (name, is_bot)) in enumerate(zip(roles, entries))
            ]
            # the wolves know each other from the start (needed to coordinate the dead vote).
            self.wolf_info = {p.id: {"faction": Faction.WOLF}
                              for p in self.players if p.faction == Faction.WOLF}
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    # ---------- queries ----------
    def player(self, pid: int) -> Player:
        try:
            p = next((x for x in self.players if x.id == pid), None)
            if p is None:
                raise GameError("Người chơi không tồn tại")
            return p
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("player failed")
            raise

    def alive(self, faction: Faction | None = None) -> list[Player]:
        try:
            return [p for p in self.players if p.alive and (faction is None or p.faction == faction)]
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("alive failed")
            raise

    def knowledge_for(self, p: Player) -> dict[int, dict[str, Any]]:
        try:
            merged = {pid: dict(info) for pid, info in self.public_info.items()}
            if p.faction == Faction.WOLF:
                for pid, info in self.wolf_info.items():
                    merged.setdefault(pid, {}).update(info)
            return merged
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("knowledge_for failed")
            raise

    def check_win(self) -> bool:
        try:
            w, v, g = (len(self.alive(f)) for f in (Faction.WOLF, Faction.VILLAGER, Faction.GHOST))
            t = w + v + g
            if t == 0:  # nobody is alive: a draw (no faction wins)
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
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("check_win failed")
            raise

    # ---------- log ----------
    def add_event(self, text: str, audience: frozenset[int] | None,
                   full_text: str | None = None) -> None:
        try:
            self.events.append(Event(len(self.events), self._round, text, audience, full_text))
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("add_event failed")
            raise

    def announce(self, text: str) -> None:
        try:
            self.add_event(text, None)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("announce failed")
            raise

    def note(self, players: Sequence[Player], text: str, full_text: str | None = None) -> None:
        try:
            self.add_event(text, frozenset(p.id for p in players), full_text)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("note failed")
            raise

    def share(self, seer: Player, target: Player, key: str, value: Any, text: str) -> None:
        """Kết quả soi: phe Sói giữ riêng cho Sói, phe khác thì công khai."""
        try:
            if seer.faction == Faction.WOLF:
                self.wolf_info.setdefault(target.id, {})[key] = value
                wolves = [x for x in self.players if x.faction == Faction.WOLF]
                self.note(wolves, f"🔮 {text}", f"🔮 (kết quả riêng của Sói) {text}")
            else:
                self.public_info.setdefault(target.id, {})[key] = value
                self.announce(f"📢 {text}")
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("share failed")
            raise

    # ---------- control ----------
    def start(self) -> None:
        try:
            if self.phase != Phase.SETUP:
                raise GameError("Game đã bắt đầu")
            self.start_night()
            self.advance()
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("start failed")
            raise

    def submit(self, pid: int, target: int, kind: str = "ability") -> None:
        """`kind`: "ability" (chức năng) hoặc "wolf" (vote giết của Sói, target 0 = bỏ phiếu trắng)."""
        try:
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
                opts = self.exclusive(pid, kind, base)
                if target in base and target not in opts:
                    raise GameError("Người này đã bị Giết trực tiếp (hoặc vote giết) rồi, hãy chọn người khác")
                if target not in opts and not (kind == "wolf" and target == 0):
                    raise GameError("Mục tiêu không hợp lệ")
                store[pid] = target
                if kind == "ability" and pid in self.wolf_options and pid not in self.wolf_actions \
                        and not self.exclusive(pid, "wolf", self.wolf_options[pid]):
                    self.wolf_actions[pid] = 0  # nobody else left to vote for: blank vote by itself
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
                self.announce(f"🏹 {p.name} kéo theo → {t.name}")
                self.kill(t, "bị kéo theo")
                self.pending_revenge = None
                self.phase = Phase.SETTLE
            else:
                raise GameError("Hiện không thể thực hiện hành động")
            self.advance()
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("submit failed")
            raise

    def force(self) -> None:
        """Host ép qua phase: người chưa chọn coi như bỏ qua."""
        try:
            if self.phase in (Phase.SETUP, Phase.OVER):
                raise GameError("Không có phase nào để bỏ qua")
            self.skipped.update(self.missing())
            if self.phase == Phase.REVENGE:
                self.pending_revenge = None
                self.phase = Phase.SETTLE
            self.advance()
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("force failed")
            raise

    def take_over(self, pid: int) -> None:
        """Người chơi rời ván: ghế chuyển cho bot (lượt đang chờ coi như bỏ qua, các lượt sau bot tự chơi)."""
        try:
            p = self.player(pid)
            if p.is_bot:
                return
            p.is_bot = True
            if self.phase in (Phase.SETUP, Phase.OVER):
                return
            if pid in self.missing():
                self.skipped.add(pid)
            if self.phase == Phase.REVENGE and self.pending_revenge == pid:
                self.pending_revenge = None
                self.phase = Phase.SETTLE
            self.advance()
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("take_over failed")
            raise

    # ---------- clock ----------
    def timer_budget(self) -> int | None:
        try:
            if not self.timer or self.phase not in (Phase.NIGHT, Phase.DAY, Phase.REVENGE):
                return None
            return self.timer * (2 if self.phase == Phase.DAY else 1)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("timer_budget failed")
            raise

    def seconds_left(self, now: float | None = None) -> float | None:
        """Số giây còn lại của lượt hiện tại (None nếu không giới hạn). Đồng hồ bắt đầu khi lượt được quan sát lần đầu."""
        try:
            budget = self.timer_budget()
            if budget is None:
                return None
            now = self._clock() if now is None else now
            key = (self.phase, self.night, self.pending_revenge)
            if key != self._timer_key:
                self._timer_key, self._timer_start = key, now
            return max(0.0, budget - (now - self._timer_start))
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("seconds_left failed")
            raise

    def tick(self, now: float | None = None) -> bool:
        """Hết giờ thì ép qua lượt (người chưa chọn bị bỏ qua). Trả về True nếu game vừa tiến lên."""
        try:
            left = self.seconds_left(now)
            if left is None or left > 0:
                return False
            self.force()
            return True
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("tick failed")
            raise

    # ---------- chat ----------
    def chat_channel_for(self, p: Player) -> str | None:
        """Kênh `p` đang được gửi tin: công khai ban ngày, Sói ban đêm, người chết luôn có kênh riêng."""
        try:
            if self.game_over:
                return "public"
            if not p.alive:
                return "public" if self.dead_talk else "dead"
            if self.phase == Phase.DAY:
                return "public"
            if self.phase == Phase.NIGHT and p.faction == Faction.WOLF:
                return "wolf"
            return None
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("chat_channel_for failed")
            raise

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
        try:
            return (everything or m.channel == "public"
                    or (m.channel == "wolf" and viewer.faction == Faction.WOLF)
                    or (m.channel == "dead" and not viewer.alive))
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("message_visible failed")
            raise

    def chat_entry(self, m: ChatMessage) -> dict[str, Any]:
        try:
            names = {x.id: x.name for x in self.players}
            return {"seq": m.seq, "round": m.round, "channel": m.channel, "text": m.text, "target": m.target,
                    "dead": m.dead, "author": {"id": m.author, "name": names.get(m.author, "?")}}
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("chat_entry failed")
            raise

    def visible_chat(self, viewer: Player, everything: bool) -> list[dict[str, Any]]:
        try:
            return [self.chat_entry(m) for m in self.chat.messages[-CHAT_SNAPSHOT:]
                    if self.message_visible(viewer, m, everything)]
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("visible_chat failed")
            raise

    def missing(self) -> list[int]:
        try:
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
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("missing failed")
            raise

    def advance(self) -> None:
        """Chạy các chuyển phase tự động cho tới khi cần người thật nhập."""
        try:
            while True:
                if self.phase == Phase.NIGHT:
                    if self.missing():
                        return
                    self.resolve_night()
                elif self.phase == Phase.DAY:
                    if self.missing():
                        return
                    self.resolve_day()
                elif self.phase == Phase.SETTLE:
                    if not self.settle_game():
                        return
                else:
                    return
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("advance failed")
            raise

    # ---------- death / end ----------
    def kill(self, p: Player, cause: str) -> None:
        try:
            if not p.alive:
                return
            p.alive = False
            p.died_on = self.night
            death: dict[str, Any] = {"id": p.id, "name": p.name, "cause": cause}
            self._deaths.append(death)
            self.announce(f"💀 {p.name} chết [{cause}]")
            if p.ability == Ability.REVEAL_ON_DEATH:
                death["revealed"] = {"faction": fac(p.faction), "ability": abi(p.ability)}
                self.public_info.setdefault(p.id, {}).update(faction=p.faction, ability=p.ability)
                self.announce(f"📢 Lộ: {p.name} = {p.faction.value}, {p.ability.value}")
            if p.ability == Ability.KILL_ON_DEATH:
                self._revenge_queue.append(p)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("kill failed")
            raise

    def check_end(self) -> bool:
        try:
            if not self.check_win():
                return False
            self.end_game()
            return True
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("check_end failed")
            raise

    def flush_recap(self, kind: str, round_no: int) -> None:
        """Gói những ai chết ở bước vừa rồi thành thẻ Bình minh (sau đêm) hoặc Hoàng hôn (sau ngày)."""
        try:
            self._recap_seq += 1
            self.recap = {"seq": self._recap_seq, "kind": kind, "round": round_no, "deaths": self._deaths}
            self._deaths = []
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("flush_recap failed")
            raise

    def end_game(self) -> None:
        try:
            if self._deaths:
                self.flush_recap("dawn" if self._last_step == "night" else "dusk", self.night)
            self.game_over = True
            self.phase = Phase.OVER
            if self.winner is None:
                self.announce("🤝 HÒA — không còn ai sống!")
            else:
                self.announce(f"🏆 PHE {self.winner.value.upper()} THẮNG!")
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("end_game failed")
            raise

    def settle_game(self) -> bool:
        """Xử lý hàng đợi giết-khi-chết. False nếu đang chờ người thật chọn."""
        try:
            while self._revenge_queue:
                p = self._revenge_queue.pop(0)
                enemies = [x for x in self.alive() if x.faction != p.faction]
                if not enemies:
                    continue
                if p.is_bot:
                    know = self.knowledge_for(p)
                    known = [x for x in enemies
                             if know.get(x.id, {}).get("faction") not in (None, p.faction)]
                    t = random.choice(known or enemies)
                    self.announce(f"🏹 {p.name} kéo theo → {t.name}")
                    self.kill(t, "bị kéo theo")
                else:
                    self.phase = Phase.REVENGE
                    self.pending_revenge = p.id
                    self.revenge_options = [x.id for x in enemies]
                    self.skipped = set()
                    return False
            if self.check_end():
                return True
            if self._next == "day":
                self.start_day()
            elif self.night >= self.max_nights:
                counts = {f: len(self.alive(f)) for f in Faction}
                self.winner = max(counts, key=lambda f: counts[f])
                self.end_game()
            else:
                self.start_night()
            return True
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("settle_game failed")
            raise

    # ---------- NIGHT ----------
    def options_for(self, p: Player) -> list[int]:
        try:
            if p.ability in PASSIVE:
                return []
            if p.ability == Ability.TRANSFORM and p.faction != Faction.GHOST:
                return []
            ids = [x.id for x in self.alive() if x.id != p.id]
            if p.ability == Ability.BLOCK_EFFECTS:  # does not protect the same person two nights in a row
                ids = [i for i in ids if i != self.last_protect_target.get(p.id)]
            return ids
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("options_for failed")
            raise

    def exclusive(self, pid: int, kind: str, ids: list[int]) -> list[int]:
        """Sói có Giết trực tiếp: người đã chọn ở hành động này bị loại khỏi hành động kia (đòn thứ hai là thừa)."""
        try:
            p = self.player(pid)
            if p.faction != Faction.WOLF or p.ability != Ability.KILL:
                return ids
            other = self.actions.get(pid) if kind == "wolf" else self.wolf_actions.get(pid)
            return [i for i in ids if i != other] if other else ids
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("exclusive failed")
            raise

    def wolf_options_for(self, p: Player) -> list[int]:
        """Mọi Sói còn sống đều có vote giết ban đêm mặc định; mục tiêu là người không phải Sói."""
        try:
            if p.faction != Faction.WOLF:
                return []
            return [x.id for x in self.alive() if x.faction != Faction.WOLF]
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("wolf_options_for failed")
            raise

    def start_night(self) -> None:
        try:
            self.night += 1
            self.phase = Phase.NIGHT
            self._round = f"Đêm {self.night}"
            if self.night > 1:
                self.flush_recap("dusk", self.night - 1)
            self.event = self.forced_event or (draw_event() if self.events_enabled else None)
            if self.event:
                self.announce(f"🎴 Sự kiện: {self.event.icon} {self.event.title} — {self.event.text}")
            self.actions, self.wolf_actions, self.skipped = {}, {}, set()
            self.night_options, self.wolf_options = {}, {}
            for p in self.alive():
                opts = self.options_for(p)
                if opts:
                    self.night_options[p.id] = opts
                    if p.is_bot:
                        self.actions[p.id] = self.auto_target(p, [self.player(i) for i in opts]).id
                wolf_opts = self.wolf_options_for(p)
                if p.ability == Ability.KILL and len(wolf_opts) == 1 and wolf_opts[0] in opts:
                    # Only one target is left and a direct Kill already aims at it: a kill vote on the same person is redundant.
                    wolf_opts = []
                if wolf_opts:
                    self.wolf_options[p.id] = wolf_opts
                    if p.is_bot:
                        choices = self.exclusive(p.id, "wolf", wolf_opts)
                        self.wolf_actions[p.id] = (
                            self.auto_wolf_target(p, [self.player(i) for i in choices]).id if choices else 0)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("start_night failed")
            raise

    def resolve_night(self) -> None:
        try:
            self._last_step = "night"
            ev = self.event.code if self.event else None
            alive_before = len(self.alive())
            acts = {pid: (self.player(pid), self.player(tid)) for pid, tid in self.actions.items()}
            for p, t in acts.values():  # the user sees the "You..." version; the full log sees the version with names
                self.add_event(f"📝 Bạn dùng {p.ability.value} lên {t.name}", frozenset({p.id}),
                                f"📝 {p.name} ({p.faction.value}, {p.ability.value}) → {t.name}")
            wolf_acts = {pid: (self.player(pid), self.player(tid))
                         for pid, tid in self.wolf_actions.items() if tid}  # tid 0 = blank vote
            for p, t in wolf_acts.values():
                self.add_event(f"📝 Bạn vote Sói lên {t.name}", frozenset({p.id}),
                                f"📝 {p.name} (Sói) vote Sói → {t.name}")
            blocked: set[int] = set()
            protected: set[int] = set()
            reflected: set[int] = set()

            def of(ability: Ability):
                # Generator: checks `blocked` at the moment it is iterated, as in the original.
                try:
                    for pid, (p, t) in list(acts.items()):
                        if p.ability == ability and pid not in blocked:
                            yield pid, p, t
                except Exception as error:
                    if getattr(error, "status_code", None) is None:
                        logger.exception("of failed")
                    raise

            for pid, p, t in of(Ability.BLOCK_ABILITY):
                blocked.add(t.id)
                self.note([p], f"🚫 Bạn khóa chức năng {t.name}", f"🚫 {p.name} khóa chức năng {t.name}")
                self.note([t], "🚫 Chức năng của bạn bị khóa đêm nay", "")

            for pid, p, t in of(Ability.REVERSE_ABILITY):
                if (t.id in acts or t.id in wolf_acts) and t.id not in blocked:
                    self.note([p], f"🔄 Bạn đảo chức năng của {t.name}",
                               f"🔄 {p.name} đảo chức năng của {t.name} (hành động của {t.name} quay về chính họ)")
                    for book in (acts, wolf_acts):  # both the ability and the wolf vote of the target
                        if t.id in book:
                            old_p, _ = book[t.id]
                            book[t.id] = (old_p, old_p)

            for pid, p, t in of(Ability.BLOCK_EFFECTS):
                protected.add(t.id)
                self.note([p], f"🛡 Bạn bảo vệ {t.name}", f"🛡 {p.name} bảo vệ {t.name}")
                self.last_protect_target[pid] = t.id

            for pid, p, t in of(Ability.REVERSE_EFFECTS):
                reflected.add(t.id)
                self.note([p], f"↩️ Bạn đặt phản đòn lên {t.name}", f"↩️ {p.name} đặt phản đòn lên {t.name}")

            if ev == "FULL_MOON":  # Full moon: protection and reflection have no effect
                protected.clear()
                reflected.clear()

            for pid, p, t in of(Ability.SEE_FACTION):
                if ev == "FOG":
                    self.note([p], "🌫️ Sương mù che mắt bạn, không thấy gì", "")
                else:
                    self.share(p, t, "faction", t.faction, f"{t.name} thuộc nhóm {t.faction.value}")
            for pid, p, t in of(Ability.SEE_ABILITY):
                if ev == "FOG":
                    self.note([p], "🌫️ Sương mù che mắt bạn, không thấy gì", "")
                else:
                    self.share(p, t, "ability", t.ability, f"{t.name} có chức năng {t.ability.value}")

            for pid, p, t in of(Ability.TRANSFORM):
                if self.transform(p, t, protected, reflected, ev):
                    return

            kill_targets: list[Player] = []
            for pid, p, t in of(Ability.KILL):
                if t.id in protected:
                    self.note([p], f"⚔️ Giết {t.name} thất bại (được bảo vệ)",
                               f"⚔️ {p.name} giết {t.name} thất bại (được bảo vệ)")
                elif t.id in reflected:
                    self.note([p], f"⚔️ Giết {t.name} bị phản đòn — bạn chết thay",
                               f"⚔️ {p.name} giết {t.name} bị phản đòn — {p.name} chết thay")
                    kill_targets.append(p)
                else:
                    kill_targets.append(t)

            kill_targets.extend(self.wolf_victims(ev, wolf_acts, blocked, protected, reflected))

            seen: set[int] = set()
            for t in kill_targets:
                if t.id not in seen:
                    seen.add(t.id)
                    self.kill(t, "bị giết ban đêm")
            if len(self.alive()) == alive_before:
                self.announce("🌅 Đêm qua yên bình, không ai chết.")
            self.phase = Phase.SETTLE
            self._next = "day"
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("resolve_night failed")
            raise

    def transform(self, p: Player, t: Player, protected: set[int], reflected: set[int], ev: str | None) -> bool:
        """A ghost turns `t` into a ghost unless `t` is protected or reflects it. True when the game ended."""
        try:
            if t.faction == Faction.GHOST:
                self.note([p], f"👻 Biến hình {t.name} thất bại (đã là Ma)",
                           f"👻 {p.name} biến hình {t.name} thất bại (đã là Ma)")
            elif t.id in protected and ev != "GHOST_NIGHT":
                self.note([p], f"👻 Biến hình {t.name} thất bại (được bảo vệ)",
                           f"👻 {p.name} biến hình {t.name} thất bại (được bảo vệ)")
            elif t.id in reflected and ev != "GHOST_NIGHT":
                self.note([p], f"👻 Biến hình {t.name} thất bại (phản đòn)",
                           f"👻 {p.name} biến hình {t.name} thất bại (phản đòn)")
            else:
                t.faction = Faction.GHOST
                self.note([p], f"👻 {t.name} đã bị biến thành Ma",
                           f"👻 {p.name} biến {t.name} thành Ma")
                self.note([t], "👻 Bạn đã bị biến thành Ma! Giờ bạn thuộc phe Ma.", "")
                return self.check_end()
            return False
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("transform failed")
            raise

    def wolf_victims(self, ev: str | None, wolf_acts: dict, blocked: set[int], protected: set[int],
                      reflected: set[int]) -> list[Player]:
        """The wolves' votes of the night: the one the most votes name dies (a tie: none, or a random one under a blood moon)."""
        try:
            wolves = [x for x in self.players if x.faction == Faction.WOLF]
            wolf_votes: dict[int, int] = {}
            if ev == "PEACEFUL" and wolf_acts:
                self.note(wolves, "🕊️ Đêm bình yên: vote giết của Sói không có hiệu lực")
            for pid, (p, t) in ({} if ev == "PEACEFUL" else wolf_acts).items():
                if pid in blocked or p.faction != Faction.WOLF:
                    continue
                if t.id in protected:
                    self.note(wolves, f"🐺 Vote của {p.name} vào {t.name} bị chặn (được bảo vệ)")
                    continue
                target_id = p.id if t.id in reflected else t.id
                if target_id == p.id:
                    self.note(wolves, f"🐺 Vote của {p.name} vào {t.name} bị phản đòn, phiếu quay về {p.name}")
                wolf_votes[target_id] = wolf_votes.get(target_id, 0) + 1
            if not wolf_votes:
                return []
            ranked = sorted(wolf_votes.items(), key=lambda kv: -kv[1])
            tally = ", ".join(f"{self.player(tid).name} {v}" for tid, v in ranked)
            top_votes = ranked[0][1]
            top = [tid for tid, v in ranked if v == top_votes]
            if len(top) == 1:
                victim = self.player(top[0])
                self.note(wolves, f"🐺 Sói vote ({tally}) → giết {victim.name}")
                return [victim]
            if ev == "BLOOD_MOON":
                victim = self.player(random.choice(top))
                self.note(wolves, f"🩸 Trăng máu: Sói vote hòa ({tally}), ngẫu nhiên chọn giết {victim.name}")
                return [victim]
            self.note(wolves, f"🐺 Sói vote ({tally}) → hòa phiếu, vote Sói không giết ai")
            return []
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("wolf_victims failed")
            raise

    def auto_target(self, p: Player, others: list[Player]) -> Player:
        try:
            know = self.knowledge_for(p)
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
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("auto_target failed")
            raise

    def auto_wolf_target(self, p: Player, others: list[Player]) -> Player:
        try:
            know = self.knowledge_for(p)
            known_enemies = [x for x in others
                             if know.get(x.id, {}).get("faction") not in (None, p.faction)]
            enemies = [x for x in others if x.faction != p.faction]
            return random.choice(known_enemies or enemies or others)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("auto_wolf_target failed")
            raise

    # ---------- DAY ----------
    def start_day(self) -> None:
        try:
            self.phase = Phase.DAY
            self._round = f"Ngày {self.night}"
            self.flush_recap("dawn", self.night)
            self.votes, self.skipped = {}, set()
            for line_bot, text, target in bots.chatter(self):  # bots speak before the vote
                self.chat.add(line_bot.id, "public", text, self._round, target, throttle=False)
            cast: dict[int, int] = {}
            day_bots = [p for p in self.alive() if p.is_bot]
            random.shuffle(day_bots)  # random order so that "following the leading faction" does not favour anyone
            for p in day_bots:
                pick = bots.day_vote(self, p, [x for x in self.alive() if x != p], cast)
                self.votes[p.id] = cast[p.id] = pick.id
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("start_day failed")
            raise

    def resolve_day(self) -> None:
        try:
            self._last_step = "day"
            self.vote_history.append(dict(self.votes))
            for voter_id, target in self.votes.items():
                voter = self.player(voter_id)
                who = self.player(target).name if target else "bỏ trắng"
                self.add_event(f"🗳 {voter.name} vote → {who}", None,
                                f"🗳 {voter.name} ({voter.faction.value}) vote → {who}")
            tally: dict[int, int] = {}
            for target in self.votes.values():
                if target:
                    tally[target] = tally.get(target, 0) + 1
            self._next = "night"
            self.phase = Phase.SETTLE
            if not tally:
                self.announce("⚖️ Không ai bị treo cổ.")
                return
            top_votes = max(tally.values())
            top = [tid for tid, v in tally.items() if v == top_votes]
            if len(top) > 1 and self.event is not None and self.event.code == "JUSTICE":
                pick = self.player(random.choice(top))
                self.announce(f"⚖️ Ngày công lý: hòa phiếu nên ngẫu nhiên chọn {pick.name}")
                top = [pick.id]
            if len(top) > 1:
                self.announce("⚖️ Hòa phiếu — không ai bị treo cổ.")
                return
            victim = self.player(top[0])
            self.announce(f"📊 {victim.name} bị treo cổ ({top_votes} phiếu)")
            self.kill(victim, "bị treo cổ")
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("resolve_day failed")
            raise

    # ---------- view cho client ----------
    def can_see_everything(self, pid: int) -> bool:
        """Chỉ người đã chết hoặc khi ván đã kết thúc mới được xem nhật ký đầy đủ / góc nhìn người khác.

        (Khác bản gốc, nơi ai cũng xem được: trên nền tảng này điều đó lộ bí mật giữa người thật.)
        """
        try:
            return self.game_over or not self.player(pid).alive
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("can_see_everything failed")
            raise

    def view_for(self, pid: int, perspective: bool = False) -> dict[str, Any]:
        """Góc nhìn của người chơi `pid`. `perspective=True`: đúng những gì người đó biết (không xem toàn bộ).

        Người còn sống chỉ thấy nhật ký của mình; người chết (và mọi người khi ván xong) thấy nhật ký đầy đủ.
        """
        try:
            me = self.player(pid)
            known = self.knowledge_for(me)
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
                    "faction": fac(faction) if faction else None,
                    "ability": abi(ability) if ability else None,
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
                "winner": fac(self.winner) if self.winner else None,
                "me": {"id": me.id, "name": me.name, "alive": me.alive,
                       "faction": fac(me.faction), "ability": abi(me.ability)},
                "players": players,
                "actions": self.actions_for(me),
                "waitingFor": len(self.missing()),
                "log": log,
                "event": self.event.view() if self.event and (self.phase == Phase.NIGHT or self.event.affects_day) else None,
                "recap": self.recap,
                "timer": self.timer_view(),
                "chat": self.visible_chat(me, everything=reveal),
                "chatChannel": self.chat_channel_for(me),
            }
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("view_for failed")
            raise

    def timer_view(self) -> dict[str, Any] | None:
        try:
            left = self.seconds_left()
            if left is None:
                return None
            return {"total": self.timer_budget(), "secondsLeft": round(left, 1)}
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("timer_view failed")
            raise

    def actions_for(self, me: Player) -> list[dict[str, Any]]:
        """Các hành động người chơi đang phải/được làm: night (chức năng), wolf (vote Sói), day, revenge."""
        try:
            def entry(kind: str, ids: list[int], store: dict[int, int], can_abstain: bool) -> dict[str, Any]:
                try:
                    return {"kind": kind, "options": ids, "submitted": me.id in store,
                            "current": store.get(me.id), "canAbstain": can_abstain}
                except Exception as error:
                    if getattr(error, "status_code", None) is None:
                        logger.exception("entry failed")
                    raise

            out: list[dict[str, Any]] = []
            if self.phase == Phase.NIGHT:
                if me.id in self.night_options:
                    out.append(entry("night", self.exclusive(me.id, "ability", self.night_options[me.id]),
                                     self.actions, False))
                if me.id in self.wolf_options:
                    out.append(entry("wolf", self.exclusive(me.id, "wolf", self.wolf_options[me.id]),
                                     self.wolf_actions, True))
            elif self.phase == Phase.DAY and me.alive:
                ids = [x.id for x in self.alive() if x.id != me.id]
                out.append(entry("day", ids, self.votes, True))
            elif self.phase == Phase.REVENGE and self.pending_revenge == me.id:
                out.append(entry("revenge", self.revenge_options, {}, False))
            return out
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("actions_for failed")
            raise
