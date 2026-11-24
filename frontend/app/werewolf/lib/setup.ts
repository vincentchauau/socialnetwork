import type { AbilityMeta, FactionCode, SetupMeta, SetupSeat } from "./types";

/** Abilities a faction may have (mirror of the server's allowedFactions). */
export function abilitiesFor(meta: SetupMeta, faction: FactionCode): AbilityMeta[] {
  return meta.abilities.filter((ability) => ability.allowedFactions.includes(faction));
}

/** Changes a seat's faction; keeps the ability if it is still allowed, else the first allowed one. */
export function pickFaction(meta: SetupMeta, seat: SetupSeat, faction: FactionCode): SetupSeat {
  if (faction === seat.faction) return seat;
  const allowed = abilitiesFor(meta, faction);
  const keep = allowed.some((ability) => ability.code === seat.ability);
  return { faction, ability: keep ? seat.ability : (allowed[0]?.code ?? "NONE") };
}

export function pickAbility(meta: SetupMeta, seat: SetupSeat, ability: string): SetupSeat {
  return abilitiesFor(meta, seat.faction).some((a) => a.code === ability) ? { ...seat, ability } : seat;
}

export function tally(seats: SetupSeat[], faction: FactionCode): number {
  return seats.filter((seat) => seat.faction === faction).length;
}
