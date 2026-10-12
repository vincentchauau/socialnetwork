"""Pure werewolf rules engine (no I/O)."""

from app.engine.lobby import add_player, new_game, role_deck, start_game
from app.engine.play import (
    cast_vote,
    check_win,
    end_discussion,
    force_advance,
    leave,
    resolve_night,
    resolve_vote,
    submit_action,
)
from app.engine.types import (
    MAX_PLAYERS,
    MIN_PLAYERS,
    Event,
    ForbiddenAction,
    Game,
    GameError,
    Phase,
    Player,
    Role,
    Winner,
)
from app.engine.views import CHAT_ALL, CHAT_WOLVES, chat_recipients, chat_scope, view_for

__all__ = [
    "CHAT_ALL", "CHAT_WOLVES", "MAX_PLAYERS", "MIN_PLAYERS", "Event", "ForbiddenAction", "Game",
    "GameError", "Phase", "Player", "Role", "Winner", "add_player", "cast_vote", "chat_recipients",
    "chat_scope", "check_win", "end_discussion", "force_advance", "leave", "new_game",
    "resolve_night", "resolve_vote", "role_deck", "start_game", "submit_action", "view_for",
]
