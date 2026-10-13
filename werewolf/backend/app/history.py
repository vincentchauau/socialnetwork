import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.models import GamePlayer, GameResult
from app.rooms import GameRecord
from app.schemas import HistoryEntry, HistoryPlayer

logger = logging.getLogger(__name__)

# Rows written by the old 4-role game (role/winner columns only) are mapped onto the new vocabulary.
_LEGACY_FACTION = {"werewolf": "WOLF", "villager": "VILLAGER", "seer": "VILLAGER", "doctor": "VILLAGER"}
_LEGACY_ABILITY = {"seer": "SEE_FACTION", "doctor": "BLOCK_EFFECTS", "villager": "NONE", "werewolf": "KILL"}
_LEGACY_WINNER = {"village": "VILLAGER", "wolves": "WOLF"}


def save_record(factory: sessionmaker, record: GameRecord) -> bool:
    """Store a finished game (one row per HUMAN player; bots are never stored). Never raises into the game loop.

    Returns True when stored (or there is nothing to store), False when the write failed, so it can be retried.
    """
    players = [
        GamePlayer(
            user_id=p.user_id, username=p.username, role=p.faction, faction=p.faction, ability=p.ability,
            outcome=p.outcome, survived=p.survived, days_survived=p.days_survived,
        )
        for p in record.players
        if p.user_id > 0  # defensive: a bot or tombstone id is never a user
    ]
    if not players:
        return True
    try:
        with factory() as session:
            session.add(GameResult(room_id=record.room_code, winner=record.winner, days=record.days,
                                   size=record.size, players=players))
            session.commit()
    except Exception:
        logger.exception("Could not save result for room %s", record.room_code)
        return False
    return True


def _normalize(player: GamePlayer, winner: str) -> HistoryPlayer:
    if player.outcome:
        return HistoryPlayer.model_validate(player)
    faction = _LEGACY_FACTION.get(player.role, player.role.upper())
    won = faction == _LEGACY_WINNER.get(winner, winner)
    return HistoryPlayer(username=player.username, faction=faction, ability=_LEGACY_ABILITY.get(player.role, ""),
                         outcome="won" if won else "lost", survived=player.survived)


def list_history(session: Session, user_id: int, limit: int) -> list[HistoryEntry]:
    stmt = (
        select(GameResult)
        .join(GamePlayer)
        .where(GamePlayer.user_id == user_id)
        .options(selectinload(GameResult.players))
        .order_by(GameResult.id.desc())
        .limit(limit)
    )
    entries: list[HistoryEntry] = []
    for result in session.scalars(stmt).unique():
        raw = next(p for p in result.players if p.user_id == user_id)
        mine = _normalize(raw, result.winner)
        entries.append(
            HistoryEntry(
                game_id=result.id,
                room_id=result.room_id,
                finished_at=result.finished_at,
                winner=_LEGACY_WINNER.get(result.winner, result.winner),
                days=result.days,
                size=result.size or len(result.players),
                your_faction=mine.faction,
                your_ability=mine.ability,
                your_outcome=mine.outcome,
                won=mine.outcome == "won",
                survived=mine.survived,
                days_survived=raw.days_survived,
                players=[_normalize(p, result.winner) for p in result.players],
            )
        )
    return entries
