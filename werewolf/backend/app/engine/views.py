"""Per-player redacted views of a game, and chat permissions.

Secrecy rules (the only places a role leaves the server):
- you always see your own role;
- living werewolves see their fellow wolves (alive or dead);
- a player's role becomes public when they die (lynch, night kill or leaving mid-game);
- when the game is finished every role is revealed.
Seer results, the doctor's last target and wolf votes go only to the player they belong to.
"""

from typing import Any

from app.engine.types import Event, Game, Phase, Player, Role

CHAT_ALL = "all"
CHAT_WOLVES = "wolves"


def _role_visible(game: Game, viewer: Player | None, subject: Player) -> bool:
    if game.phase is Phase.FINISHED or not subject.alive:
        return True
    if viewer is None or viewer.left:
        return False
    if viewer.user_id == subject.user_id:
        return True
    return viewer.role is Role.WEREWOLF and subject.role is Role.WEREWOLF and viewer.alive


def _player_view(game: Game, viewer: Player | None, subject: Player) -> dict[str, Any]:
    visible = _role_visible(game, viewer, subject) and subject.role is not None
    return {
        "id": subject.user_id,
        "username": subject.username,
        "alive": subject.alive,
        "left": subject.left,
        "is_host": subject.user_id == game.host_id,
        "role": subject.role.value if visible and subject.role else None,
    }


def _event_view(game: Game, event: Event) -> dict[str, Any]:
    subject = game.find(event.player_id) if event.player_id is not None else None
    return {
        "day": event.day,
        "kind": event.kind,
        "player": subject.username if subject else None,
        "role": event.role,
    }


def pending_action(game: Game, viewer: Player | None) -> str | None:
    """The action this viewer can still take right now, or None."""
    if viewer is None or not viewer.alive or viewer.left:
        return None
    if game.phase is Phase.VOTE:
        voted = {v for v, _ in game.votes}
        return None if viewer.user_id in voted else "vote"
    if game.phase is not Phase.NIGHT:
        return None
    if viewer.role is Role.WEREWOLF:
        return "kill"  # wolves may revise their vote until the night resolves
    if viewer.role is Role.SEER:
        return "inspect" if game.seer_target is None else None
    if viewer.role is Role.DOCTOR:
        return "protect" if game.doctor_target is None else None
    return None


def _own_target(game: Game, viewer: Player) -> int | None:
    if game.phase is Phase.VOTE:
        return dict(game.votes).get(viewer.user_id)
    if game.phase is not Phase.NIGHT:
        return None
    if viewer.role is Role.WEREWOLF:
        return dict(game.wolf_votes).get(viewer.user_id)
    if viewer.role is Role.SEER:
        return game.seer_target
    if viewer.role is Role.DOCTOR:
        return game.doctor_target
    return None


def view_for(game: Game, user_id: int) -> dict[str, Any]:
    """The state as `user_id` is allowed to see it. Non-members get names only."""
    viewer = game.member(user_id)
    view: dict[str, Any] = {
        "version": game.version,
        "phase": game.phase.value,
        "day": game.day,
        "host_id": game.host_id,
        "winner": game.winner.value if game.winner else None,
        "players": [_player_view(game, viewer, p) for p in game.members()],
        "events": [_event_view(game, e) for e in game.events],
        "you": None,
    }
    if viewer is None:
        return view
    view["you"] = {
        "id": viewer.user_id,
        "role": viewer.role.value if viewer.role else None,
        "alive": viewer.alive,
        "pending": pending_action(game, viewer),
        "target": _own_target(game, viewer),
        "chat": chat_scope(game, user_id),
    }
    if viewer.role is Role.SEER:
        view["you"]["inspections"] = [
            {"id": t, "is_werewolf": wolf} for t, wolf in game.seer_results
        ]
    if viewer.role is Role.DOCTOR:
        view["you"]["blocked_target"] = game.last_doctor_target
    return view


def chat_scope(game: Game, user_id: int) -> str | None:
    """Which channel this user may currently write to (None = muted)."""
    player = game.member(user_id)
    if player is None:
        return None
    if game.phase in (Phase.LOBBY, Phase.FINISHED):
        return CHAT_ALL
    if not player.alive:
        return None
    if game.phase in (Phase.DAY, Phase.VOTE):
        return CHAT_ALL
    return CHAT_WOLVES if player.role is Role.WEREWOLF else None


def chat_recipients(game: Game, scope: str) -> frozenset[int]:
    if scope == CHAT_WOLVES:
        return frozenset(p.user_id for p in game.living(Role.WEREWOLF) if not p.left)
    return frozenset(p.user_id for p in game.members())
