import { abilityIcon, FACTION_ICON } from "../lib/theme";
import type { Game, RoomState } from "../lib/types";
import Avatar from "./Avatar";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";

interface Props {
  room: RoomState;
  game: Game;
  busy: boolean;
  onRematch: () => void;
  onReset: () => void;
}

function outcomeText(game: Game): string {
  if (!game.winner) return tr("hoa_2");
  return game.winner.code === game.me.faction.code ? tr("ban_thang") : tr("ban_thua");
}

/** End of game: winner faction, your result, win stats of the room, every player's role, rematch (host). */
export default function ResultView({ room, game, busy, onRematch, onReset }: Props) {
  const { history } = room;
  const tone = game.winner ? game.winner.code.toLowerCase() : "draw";
  return (
    <section className={`card ww-result ww-tone-${tone}`} aria-labelledby="ww-result-title">
      <span className="ww-big" aria-hidden="true">
        {game.winner ? FACTION_ICON[game.winner.code] : "🤝"}
      </span>
      <h2 id="ww-result-title">{game.winner ? tr("phe_p0_thang_2", { p0: game.winner.label }) : tr("hoa_khong_con_ai_song")}</h2>
      <p role="status">
        <strong>{outcomeText(game)}</strong>
      </p>
      {history.games > 0 && (
        <p className="muted">
          📊 {history.games} {tr("van")} {history.VILLAGER} · 🐺 {history.WOLF} · 👻 {history.GHOST} · 🤝 {history.draw}
        </p>
      )}
      <h3>{tr("vai_cua_moi_nguoi")}</h3>
      <ul className="ww-reveal ww-plain-list">
        {game.players.map((p) => (
          <li key={p.id} className={p.alive ? "" : "ww-struck"}>
            <Avatar name={p.name} size={32} tone={p.faction?.code.toLowerCase()} dead={!p.alive} />
            <strong>{p.id === game.me.id ? `${p.name} ★` : p.name}</strong>
            <span>
              {p.faction ? `${FACTION_ICON[p.faction.code]} ${p.faction.label}` : ""}{" "}
              {p.ability ? `· ${abilityIcon(p.ability.code)} ${p.ability.label}` : ""}
            </span>
            <span className="sr-only">{p.alive ? tr("con_song") : tr("da_chet_2")}</span>
          </li>
        ))}
      </ul>
      {room.isHost ? (
        <div className="stack">
          <Button type="button" disabled={busy} onClick={onRematch}>
            {tr("choi_lai_chia_vai_moi")}
          </Button>
          <Button variant="secondary" type="button" className="secondary" disabled={busy} onClick={onReset}>
            {tr("ve_phong_cho")}
          </Button>
        </div>
      ) : (
        <p className="muted">{tr("cho_chu_phong_choi_lai")}</p>
      )}
    </section>
  );
}
