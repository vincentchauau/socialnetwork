import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sn_shared import directory

from api.werewolf.models import FINISHED, Game, ids_text, utcnow
from api.werewolf.rolecode import role_code, role_parts
from api.werewolf.rooms import GameRecord
from api.werewolf.schemas import HistoryEntry, HistoryPlayer, LeaderEntry

logger = logging.getLogger(__name__)

# Rows written by the old 4-role game (role/winner columns only) are mapped onto the new vocabulary.
LEGACY_FACTION = {"werewolf": "WOLF", "villager": "VILLAGER", "seer": "VILLAGER", "doctor": "VILLAGER"}
LEGACY_ABILITY = {"seer": "SEE_FACTION", "doctor": "BLOCK_EFFECTS", "villager": "NONE", "werewolf": "KILL"}
LEGACY_WINNER = {"village": "VILLAGER", "wolves": "WOLF"}


def save_record(factory: sessionmaker, record: GameRecord) -> bool:
    """Store a finished game (the HUMAN players only; bots are never stored). Never raises into the game loop.

    Returns True when stored (or there is nothing to store), False when the write failed, so it can be retried.
    """
    players = [
        {
            "user_id": p.user_id, "role": role_code(p.faction, p.ability),
            "outcome": p.outcome, "survived": p.survived, "days_survived": p.days_survived,
        }
        for p in record.players
        if p.user_id > 0  # defensive: a bot or tombstone id is never a user
    ]
    if not players:
        return True
    try:
        with factory() as session:
            session.add(Game(
                room_code=record.room_code, status=FINISHED, winner=record.winner, days=record.days, size=record.size,
                finished_at=utcnow(), players=players, player_ids=ids_text(p["user_id"] for p in players),
            ))
            session.commit()
    except Exception:
        logger.exception("Could not save result for room %s", record.room_code)
        return False
    return True


def normalize(player: dict, winner: str, username: str) -> HistoryPlayer:
    try:
        role, outcome, survived = player.get("role", ""), player.get("outcome", ""), bool(player.get("survived"))
        parts = role_parts(role)
        if parts and outcome:
            return HistoryPlayer(username=username, faction=parts[0], ability=parts[1], outcome=outcome, survived=survived)
        if outcome:  # written between the two formats: the faction alone, the ability is not known
            return HistoryPlayer(username=username, faction=role, ability="", outcome=outcome, survived=survived)
        faction = LEGACY_FACTION.get(role, role.upper())
        won = faction == LEGACY_WINNER.get(winner, winner)
        return HistoryPlayer(username=username, faction=faction, ability=LEGACY_ABILITY.get(role, ""),
                             outcome="won" if won else "lost", survived=survived)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("normalize failed")
        raise


def list_history(session: Session, user_id: int, limit: int) -> list[HistoryEntry]:
    try:
        stmt = (
            select(Game)
            .where(Game.status == FINISHED, Game.player_ids.like(f"%|{int(user_id)}|%"))
            .order_by(Game.id.desc())
            .limit(limit)
        )
        entries: list[HistoryEntry] = []
        games = list(session.scalars(stmt))
        usernames = directory.names(session, [p["user_id"] for game in games for p in game.players])
        for game in games:
            raw = next(p for p in game.players if p["user_id"] == user_id)
            mine = normalize(raw, game.winner, usernames[raw["user_id"]])
            entries.append(
                HistoryEntry(
                    game_id=game.id,
                    room_id=game.room_code,
                    finished_at=game.finished_at,
                    winner=LEGACY_WINNER.get(game.winner, game.winner),
                    days=game.days,
                    size=game.size or len(game.players),
                    your_faction=mine.faction,
                    your_ability=mine.ability,
                    your_outcome=mine.outcome,
                    won=mine.outcome == "won",
                    survived=mine.survived,
                    days_survived=raw.get("days_survived", 0),
                    players=[normalize(p, game.winner, usernames[p["user_id"]]) for p in game.players],
                )
            )
        return entries
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("list_history failed")
        raise


LEADERBOARD_SCAN = 2000  # how many of the latest finished games the ranking is made from
LEADERBOARD_TOP = 10


def season_start(now: datetime | None = None) -> datetime:
    """The first moment of the month (UTC): a season is a month."""
    try:
        now = now or datetime.now(timezone.utc)
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("season_start failed")
        raise


def leaderboard(session: Session, top: int = LEADERBOARD_TOP, since: datetime | None = None) -> list[LeaderEntry]:
    """The people who won most of the latest finished games (only those since `since` when given: the season) (bots are never stored; a deleted account is not ranked): wins first, then fewer games."""
    try:
        tally: dict[int, list[int]] = {}  # user id -> [games, wins]
        query = select(Game).where(Game.status == FINISHED)
        if since is not None:
            query = query.where(Game.finished_at >= since)
        for game in session.scalars(query.order_by(Game.id.desc()).limit(LEADERBOARD_SCAN)):
            for raw in game.players:
                user_id = raw.get("user_id", 0)
                if not isinstance(user_id, int) or user_id <= 0:
                    continue
                row = tally.setdefault(user_id, [0, 0])
                row[0] += 1
                row[1] += normalize(raw, game.winner, "").outcome == "won"
        ranked = sorted(((user_id, games, wins) for user_id, (games, wins) in tally.items() if wins > 0), key=lambda item: (-item[2], item[1], item[0]))[:top]
        names = directory.names(session, [user_id for user_id, _, _ in ranked])
        return [LeaderEntry(username=names[user_id], games=games, wins=wins) for user_id, games, wins in ranked]
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("leaderboard failed")
        raise
