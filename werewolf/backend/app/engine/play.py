"""In-game transitions: night actions, day vote, win checks, leaving.

Rules
- Night: every living werewolf votes for a victim (they may change their vote), the seer inspects
  one player and the doctor protects one player (once each per night). The night resolves as soon as
  everyone who must act has acted, or when the host forces it. Wolves kill the victim with a unique
  plurality of wolf votes; a tie or no votes means nobody is attacked. A protected victim survives,
  and the doctor cannot protect the same player two nights in a row (self-protection is allowed).
- Day: free discussion until the host ends it, then a vote. The player with a unique plurality of
  votes is lynched; a tie for first place (or no votes) means nobody is lynched. Abstaining is allowed.
- Win: villagers win when no wolf lives; wolves win when they equal or outnumber the others.
"""

from collections import Counter
from dataclasses import replace

from app.engine.types import (
    Event,
    ForbiddenAction,
    Game,
    GameError,
    Phase,
    Player,
    Role,
    Winner,
    set_pair,
)


def _living_target(game: Game, target_id: int) -> Player:
    target = game.find(target_id)
    if target is None or not target.alive:
        raise GameError("Choose a living player")
    return target


def _actor(game: Game, actor_id: int, phase: Phase) -> Player:
    if game.phase is not phase:
        raise GameError(f"That is not allowed during the {game.phase.value} phase")
    actor = game.member(actor_id)
    if actor is None:
        raise ForbiddenAction("You are not in this game")
    if not actor.alive:
        raise GameError("Dead players cannot act")
    return actor


def check_win(game: Game) -> Game:
    wolves = len(game.living(Role.WEREWOLF))
    others = len(game.living()) - wolves
    if wolves == 0:
        winner = Winner.VILLAGE
    elif wolves >= others:
        winner = Winner.WOLVES
    else:
        return game
    finished = replace(game, phase=Phase.FINISHED, winner=winner, wolf_votes=(), votes=())
    return finished.with_event(Event(game.day, "game_over"))


def submit_action(game: Game, actor_id: int, target_id: int) -> Game:
    actor = _actor(game, actor_id, Phase.NIGHT)
    target = _living_target(game, target_id)
    if actor.role is Role.WEREWOLF:
        if target.role is Role.WEREWOLF:
            raise GameError("Werewolves cannot target each other")
        updated = replace(game, wolf_votes=set_pair(game.wolf_votes, actor_id, target_id))
    elif actor.role is Role.SEER:
        if game.seer_target is not None:
            raise GameError("You already inspected someone tonight")
        if target_id == actor_id:
            raise GameError("You cannot inspect yourself")
        updated = replace(game, seer_target=target_id)
    elif actor.role is Role.DOCTOR:
        if game.doctor_target is not None:
            raise GameError("You already protected someone tonight")
        if target_id == game.last_doctor_target:
            raise GameError("You cannot protect the same player two nights in a row")
        updated = replace(game, doctor_target=target_id)
    else:
        raise GameError("Your role has no night action")
    return resolve_night(updated) if _night_complete(updated) else updated


def _night_complete(game: Game) -> bool:
    voted = {voter for voter, _ in game.wolf_votes}
    if any(w.user_id not in voted for w in game.living(Role.WEREWOLF)):
        return False
    if game.living(Role.SEER) and game.seer_target is None:
        return False
    return not (game.living(Role.DOCTOR) and game.doctor_target is None)


def _wolf_victim(game: Game, forced: bool = False) -> int | None:
    wolves = {w.user_id for w in game.living(Role.WEREWOLF)}
    counts = Counter(t for v, t in game.wolf_votes if t is not None and v in wolves)
    leader = _unique_leader(counts)
    if forced and (leader is None or counts[leader] * 2 <= len(wolves)):
        return None  # a forced night needs the wolves' strict majority, not a lone vote
    return leader


def _unique_leader(counts: Counter[int]) -> int | None:
    ranked = counts.most_common(2)
    if not ranked:
        return None
    if len(ranked) == 2 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def resolve_night(game: Game, forced: bool = False) -> Game:
    """End the night. `forced` (host override) applies only what living role holders submitted."""
    if game.phase is not Phase.NIGHT:
        raise GameError("It is not night")
    seer_target = game.seer_target if game.living(Role.SEER) else None
    doctor_target = game.doctor_target if game.living(Role.DOCTOR) else None
    results = game.seer_results
    if seer_target is not None:
        inspected = game.find(seer_target)
        if inspected is not None:
            results += ((inspected.user_id, inspected.role is Role.WEREWOLF),)
    victim_id = _wolf_victim(game, forced)
    resolved = replace(
        game,
        phase=Phase.DAY,
        wolf_votes=(),
        votes=(),
        seer_target=None,
        doctor_target=None,
        last_doctor_target=doctor_target,
        seer_results=results,
    )
    victim = None if victim_id is None else game.find(victim_id)
    if victim is None or victim_id == doctor_target:
        return check_win(resolved.with_event(Event(game.day, "peaceful_night")))
    resolved = resolved.with_player(replace(victim, alive=False))
    event = Event(game.day, "night_death", victim.user_id, victim.role.value if victim.role else None)
    return check_win(resolved.with_event(event))


def end_discussion(game: Game, requester_id: int) -> Game:
    _require_host(game, requester_id)
    if game.phase is not Phase.DAY:
        raise GameError("It is not the discussion phase")
    return replace(game, phase=Phase.VOTE, votes=())


def cast_vote(game: Game, voter_id: int, target_id: int | None) -> Game:
    _actor(game, voter_id, Phase.VOTE)
    if target_id is not None:
        _living_target(game, target_id)
        if target_id == voter_id:
            raise GameError("You cannot vote for yourself")
    updated = replace(game, votes=set_pair(game.votes, voter_id, target_id))
    return resolve_vote(updated) if _vote_complete(updated) else updated


def _vote_complete(game: Game) -> bool:
    voted = {voter for voter, _ in game.votes}
    return all(p.user_id in voted for p in game.living())


def resolve_vote(game: Game, forced: bool = False) -> Game:
    """Tally the vote. A forced tally (host override) lynches only on a strict majority of the living."""
    if game.phase is not Phase.VOTE:
        raise GameError("It is not the voting phase")
    living = {p.user_id for p in game.living()}
    counts = Counter(t for v, t in game.votes if t is not None and v in living)
    target_id = _unique_leader(counts)
    if forced and target_id is not None and counts[target_id] * 2 <= len(living):
        target_id = None
    target = None if target_id is None else game.find(target_id)
    if target is None:
        resolved = game.with_event(Event(game.day, "no_lynch"))
    else:
        role = target.role.value if target.role else None
        resolved = game.with_player(replace(target, alive=False))
        resolved = resolved.with_event(Event(game.day, "lynch", target.user_id, role))
    resolved = replace(resolved, votes=())
    finished = check_win(resolved)
    if finished.phase is Phase.FINISHED:
        return finished
    return replace(finished, phase=Phase.NIGHT, day=game.day + 1)


def _require_host(game: Game, requester_id: int) -> None:
    if requester_id != game.host_id:
        raise ForbiddenAction("Only the host can do that")


def force_advance(game: Game, requester_id: int) -> Game:
    """Host control: end the current phase now, counting only what has been submitted."""
    _require_host(game, requester_id)
    if game.phase is Phase.NIGHT:
        return resolve_night(game, forced=True)
    if game.phase is Phase.DAY:
        return end_discussion(game, requester_id)
    if game.phase is Phase.VOTE:
        return resolve_vote(game, forced=True)
    raise GameError("There is nothing to advance")


def _next_host(game: Game, leaving_id: int) -> int:
    candidates = [p for p in game.members() if p.user_id != leaving_id]
    preferred = [p for p in candidates if p.alive] or candidates
    return preferred[0].user_id if preferred else leaving_id


def leave(game: Game, user_id: int) -> Game:
    """Leave the room. In a running game the player is eliminated but stays on the record."""
    player = game.member(user_id)
    if player is None:
        raise GameError("You are not in this room")
    host_id = _next_host(game, user_id) if game.host_id == user_id else game.host_id
    if game.phase in (Phase.LOBBY, Phase.FINISHED):
        remaining = tuple(p for p in game.players if p.user_id != user_id)
        return replace(game, players=remaining, host_id=host_id)
    return _eliminate(replace(game, host_id=host_id), player)


def _eliminate(game: Game, player: Player) -> Game:
    was_alive = player.alive
    updated = game.with_player(replace(player, alive=False, left=True))
    updated = replace(
        updated,
        wolf_votes=tuple((v, t) for v, t in updated.wolf_votes if v != player.user_id and t != player.user_id),
        votes=tuple((v, t) for v, t in updated.votes if v != player.user_id and t != player.user_id),
        seer_target=None if updated.seer_target == player.user_id else updated.seer_target,
        doctor_target=None if updated.doctor_target == player.user_id else updated.doctor_target,
    )
    if not was_alive:
        return updated
    role = player.role.value if player.role else None
    checked = check_win(updated.with_event(Event(game.day, "left", player.user_id, role)))
    if checked.phase is Phase.NIGHT and _night_complete(checked):
        return resolve_night(checked)
    if checked.phase is Phase.VOTE and _vote_complete(checked):
        return resolve_vote(checked)
    return checked
