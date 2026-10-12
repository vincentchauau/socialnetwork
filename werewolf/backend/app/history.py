import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.engine import Game, Role, Winner
from app.models import GamePlayer, GameResult
from app.schemas import HistoryEntry, HistoryPlayer

logger = logging.getLogger(__name__)


def _faction_winner(role: Role) -> Winner:
    return Winner.WOLVES if role is Role.WEREWOLF else Winner.VILLAGE


def save_result(factory: sessionmaker, room_id: str, game: Game) -> bool:
    """Store a finished game (winner, roles, players). Never raises into the game loop.

    Returns True when the result is stored (or there is nothing to store), False when the write
    failed, so the caller can retry later.
    """
    if game.winner is None:
        return True
    try:
        with factory() as session:
            players = [
                GamePlayer(
                    user_id=p.user_id,
                    username=p.username,
                    role=p.role.value if p.role else "",
                    survived=p.alive,
                )
                for p in game.players
            ]
            session.add(
                GameResult(room_id=room_id, winner=game.winner.value, days=game.day, players=players)
            )
            session.commit()
    except Exception:
        logger.exception("Could not save result for room %s", room_id)
        return False
    return True


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
        mine = next(p for p in result.players if p.user_id == user_id)
        won = bool(mine.role) and _faction_winner(Role(mine.role)).value == result.winner
        entries.append(
            HistoryEntry(
                room_id=result.room_id,
                finished_at=result.finished_at,
                winner=result.winner,
                days=result.days,
                your_role=mine.role,
                won=won,
                players=[HistoryPlayer.model_validate(p) for p in result.players],
            )
        )
    return entries
