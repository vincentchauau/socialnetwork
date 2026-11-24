import { abilitiesFor, pickAbility, pickFaction } from "../lib/setup";
import { abilityIcon, FACTION_ICON } from "../lib/theme";
import type { SetupMeta, SetupSeat } from "../lib/types";
import Avatar from "./Avatar";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import Select from "@sn/elements/Select";

interface Props {
  index: number;
  seat: SetupSeat;
  meta: SetupMeta;
  /** The name of the seat (a person, or a bot). */
  name: string;
  isBot: boolean;
  onChange: (next: SetupSeat) => void;
}

export default function SeatRow({ index, seat, meta, name, isBot, onChange }: Props) {
  const abilities = abilitiesFor(meta, seat.faction);
  const defaults = meta.defaults[seat.faction] ?? [];
  const number = index + 1;
  const abilityId = `ww-seat-${number}-ability`;

  return (
    <li className="ww-seat">
      <div className="ww-seat-id">
        <Avatar name={name} size={44} tone={seat.faction.toLowerCase()} badge={FACTION_ICON[seat.faction]} />
        <span className={isBot ? "muted" : "ww-me"}>
          #{number}
          {isBot ? "" : " ★"}
        </span>
      </div>
      <div className="ww-seat-body">
        <strong>{name}</strong>
        <div className="ww-chips" role="radiogroup" aria-label={tr("phe_cua_ghe_number", { number })}>
          {meta.factions.map((faction) => (
            <Button variant="secondary"
              key={faction.code}
              type="button"
              role="radio"
              aria-checked={seat.faction === faction.code}
              className={`ww-chip ${seat.faction === faction.code ? "" : "secondary"}`}
              onClick={() => onChange(pickFaction(meta, seat, faction.code))}
            >
              {FACTION_ICON[faction.code]} {faction.label}
            </Button>
          ))}
        </div>
        {abilities.length > 1 ? (
          <div className="ww-ability-pick">
            <label htmlFor={abilityId}>{tr("chuc_nang_ghe")} {number}</label>
            <Select id={abilityId} value={seat.ability} onChange={(event) => onChange(pickAbility(meta, seat, event.target.value))}>
              {abilities.map((ability) => (
                <option key={ability.code} value={ability.code}>
                  {abilityIcon(ability.code)} {ability.label}
                </option>
              ))}
            </Select>
          </div>
        ) : (
          <span className="ww-chip ww-locked">
            {abilityIcon(seat.ability)} {abilities[0]?.label ?? seat.ability} {tr("co_dinh")}
          </span>
        )}
        {defaults.length > 0 && (
          <ul className="ww-chips ww-plain-list" aria-label={tr("mac_dinh_cua_phe_ghe_number", { number })}>
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
