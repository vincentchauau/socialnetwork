import { abilityIcon, FACTION_ICON } from "../lib/theme";
import type { Player } from "../lib/types";
import Avatar from "./Avatar";

interface Props {
  player: Player;
  isYou?: boolean;
  disabled?: boolean;
  onPick?: () => void;
}

function describe(player: Player, isYou: boolean): string {
  const parts = [isYou ? `${player.name} (bạn)` : player.name];
  parts.push(player.alive ? "còn sống" : "đã chết");
  if (player.faction) parts.push(`phe ${player.faction.label}`);
  if (player.ability) parts.push(player.ability.label);
  return parts.join(", ");
}

/** A player: avatar, name, faction and ability only when the server told us. A button when `onPick` is given. */
export default function PlayerTile({ player, isYou = false, disabled = false, onPick }: Props) {
  const body = (
    <>
      <Avatar
        name={player.name}
        tone={player.faction?.code.toLowerCase()}
        badge={player.faction ? FACTION_ICON[player.faction.code] : undefined}
        dead={!player.alive}
      />
      <span className={`ww-tile-name${player.alive ? "" : " ww-struck"}`}>{isYou ? `${player.name} ★` : player.name}</span>
      <span className="ww-tile-ability" aria-hidden="true">
        {player.ability ? abilityIcon(player.ability.code) : ""}
      </span>
    </>
  );
  if (!onPick) {
    return (
      <li className="ww-tile" aria-label={describe(player, isYou)}>
        {body}
      </li>
    );
  }
  return (
    <li className="ww-tile-item">
      <button
        type="button"
        className="ww-tile ww-tile-button"
        disabled={disabled}
        onClick={onPick}
        aria-label={describe(player, isYou)}
      >
        {body}
      </button>
    </li>
  );
}
