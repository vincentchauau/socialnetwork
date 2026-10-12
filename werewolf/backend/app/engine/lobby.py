"""Lobby transitions: create, join, start."""

import random
from dataclasses import replace

from app.engine.types import (
    MAX_PLAYERS,
    MIN_PLAYERS,
    PLAYERS_PER_WOLF,
    ForbiddenAction,
    Game,
    GameError,
    Phase,
    Player,
    Role,
)


def new_game(host_id: int, username: str) -> Game:
    return Game(players=(Player(host_id, username),), host_id=host_id)


def add_player(game: Game, user_id: int, username: str) -> Game:
    if game.phase is not Phase.LOBBY:
        raise GameError("The game has already started")
    if game.member(user_id) is not None:
        raise GameError("You are already in this room")
    if len(game.members()) >= MAX_PLAYERS:
        raise GameError("The room is full")
    others = tuple(p for p in game.players if p.user_id != user_id)  # drop a stale `left` entry
    return replace(game, players=others + (Player(user_id, username),))


def role_deck(player_count: int) -> tuple[Role, ...]:
    """The roles for a game of this size (unshuffled)."""
    wolves = max(1, player_count // PLAYERS_PER_WOLF)
    villagers = player_count - wolves - 2
    return (
        (Role.WEREWOLF,) * wolves + (Role.SEER, Role.DOCTOR) + (Role.VILLAGER,) * villagers
    )


def start_game(game: Game, requester_id: int, rng: random.Random) -> Game:
    if requester_id != game.host_id:
        raise ForbiddenAction("Only the host can start the game")
    if game.phase is not Phase.LOBBY:
        raise GameError("The game has already started")
    if len(game.players) < MIN_PLAYERS:
        raise GameError(f"At least {MIN_PLAYERS} players are needed")
    deck = list(role_deck(len(game.players)))
    rng.shuffle(deck)
    players = tuple(replace(p, role=role) for p, role in zip(game.players, deck))
    return replace(game, players=players, phase=Phase.NIGHT, day=1)
