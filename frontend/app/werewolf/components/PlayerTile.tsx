import { abilityIcon, FACTION_ICON } from "../lib/theme";
import type { Player } from "../lib/types";
import Avatar from "./Avatar";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";

interface Props {
  player: Player;
  isYou?: boolean;
  disabled?: boolean;
  onPick?: () => void;
}

function describe(player: Player, isYou: boolean): string {
  const parts = [isYou ? tr("p0_ban", { p0: player.name }) : player.name];
  parts.push(player.alive ? tr("con_song") : tr("da_chet_2"));
  if (player.faction) parts.push(tr("phe_p0", { p0: player.faction.label }));
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
      <Button
        type="button"
        className="ww-tile ww-tile-button"
        disabled={disabled}
        onClick={onPick}
        aria-label={describe(player, isYou)}
      >
        {body}
      </Button>
    </li>
  );
}
