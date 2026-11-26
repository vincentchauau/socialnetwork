"""The role a player started with (a faction and an ability) as ONE short code, kept in the `role` of each player of a finished game (`games.players`).

The faction and the ability are not stored apart: both are read back from this code ("W:K" = wolf, kills), so a row
never holds what its role already says. The legacy values of the old 4-role game (werewolf, villager, ...) have no ":".
"""

from api.werewolf.engine.roles import Ability, Faction

_ABILITY_CODES: dict[Ability, str] = {
    Ability.NONE: "N",
    Ability.BLOCK_EFFECTS: "BE",
    Ability.REVERSE_EFFECTS: "RE",
    Ability.BLOCK_ABILITY: "BA",
    Ability.REVERSE_ABILITY: "RA",
    Ability.KILL: "K",
    Ability.KILL_ON_DEATH: "KD",
    Ability.SEE_FACTION: "SF",
    Ability.SEE_ABILITY: "SA",
    Ability.REVEAL_ON_DEATH: "RD",
    Ability.TRANSFORM: "T",
}
assert set(_ABILITY_CODES) == set(Ability), "every ability needs a role code"
FACTION_BY_LETTER = {faction.name[0]: faction for faction in Faction}
ABILITY_BY_CODE = {code: ability for ability, code in _ABILITY_CODES.items()}


def role_code(faction: str, ability: str) -> str:
    """The code of a role from the names of its faction and ability (e.g. "WOLF", "KILL" -> "W:K")."""
    return f"{Faction[faction].name[0]}:{_ABILITY_CODES[Ability[ability]]}"


def role_parts(role: str) -> tuple[str, str] | None:
    """(faction name, ability name) of a role code, or None when it is not one (a legacy row)."""
    letter, _, code = role.partition(":")
    faction, ability = FACTION_BY_LETTER.get(letter), ABILITY_BY_CODE.get(code)
    if not code or faction is None or ability is None:
        return None
    return faction.name, ability.name
