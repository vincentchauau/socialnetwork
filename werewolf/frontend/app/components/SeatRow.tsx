import { abilitiesFor, pickAbility, pickFaction } from "../lib/setup";
import { abilityIcon, FACTION_ICON } from "../lib/theme";
import type { SetupMeta, SetupSeat } from "../lib/types";
import Avatar from "./Avatar";

interface Props {
  index: number;
  seat: SetupSeat;
  meta: SetupMeta;
  /** Seat 1 is the creator: named after the account, not editable. */
  name: string | null;
  onChange: (next: SetupSeat) => void;
}

export default function SeatRow({ index, seat, meta, name, onChange }: Props) {
  const abilities = abilitiesFor(meta, seat.faction);
  const defaults = meta.defaults[seat.faction] ?? [];
  const number = index + 1;
  const abilityId = `ww-seat-${number}-ability`;

  return (
    <li className="ww-seat">
      <div className="ww-seat-id">
        <Avatar name={name ?? `Bot ${number}`} size={44} tone={seat.faction.toLowerCase()} badge={FACTION_ICON[seat.faction]} />
        <span className={name ? "ww-me" : "muted"}>
          #{number}
          {name ? " ★" : ""}
        </span>
      </div>
      <div className="ww-seat-body">
        <strong>{name ?? `Bot ${number}`}</strong>
        <div className="ww-chips" role="radiogroup" aria-label={`Phe của ghế ${number}`}>
          {meta.factions.map((faction) => (
            <button
              key={faction.code}
              type="button"
              role="radio"
              aria-checked={seat.faction === faction.code}
              className={`ww-chip ${seat.faction === faction.code ? "" : "secondary"}`}
              onClick={() => onChange(pickFaction(meta, seat, faction.code))}
            >
              {FACTION_ICON[faction.code]} {faction.label}
            </button>
          ))}
        </div>
        {abilities.length > 1 ? (
          <div className="ww-ability-pick">
            <label htmlFor={abilityId}>Chức năng ghế {number}</label>
            <select id={abilityId} value={seat.ability} onChange={(event) => onChange(pickAbility(meta, seat, event.target.value))}>
              {abilities.map((ability) => (
                <option key={ability.code} value={ability.code}>
                  {abilityIcon(ability.code)} {ability.label}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <span className="ww-chip ww-locked">
            {abilityIcon(seat.ability)} {abilities[0]?.label ?? seat.ability} (cố định)
          </span>
        )}
        {defaults.length > 0 && (
          <ul className="ww-chips ww-plain-list" aria-label={`Mặc định của phe, ghế ${number}`}>
            {defaults.map((chip) => (
              <li key={chip.label} className="ww-chip ww-locked" title={chip.hint}>
                🔒 {chip.icon} {chip.label}
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}
