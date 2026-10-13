"""Ma Sói rules engine (3 factions, 11 abilities): pure logic, no I/O."""

from app.engine.game import MAX_TIMER, MIN_TIMER, Event, Game, Phase, Player
from app.engine.help_text import ABILITY_HELP, help_payload
from app.engine.roles import (
    ALLOWED_ABILITIES,
    DEFAULT_ABILITIES,
    MAX_PLAYERS,
    MIN_PLAYERS,
    Ability,
    Faction,
    GameError,
    Role,
    suggest_roles,
    validate_roles,
)

__all__ = [
    "ABILITY_HELP", "ALLOWED_ABILITIES", "DEFAULT_ABILITIES", "MAX_PLAYERS", "MAX_TIMER", "MIN_PLAYERS",
    "MIN_TIMER", "Ability", "Event", "Faction", "Game", "GameError", "Phase", "Player", "Role",
    "help_payload", "suggest_roles", "validate_roles",
]
