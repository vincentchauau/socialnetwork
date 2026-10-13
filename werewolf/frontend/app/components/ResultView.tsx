import { abilityIcon, FACTION_ICON } from "../lib/theme";
import type { Game, RoomState } from "../lib/types";
import Avatar from "./Avatar";

interface Props {
  room: RoomState;
  game: Game;
  busy: boolean;
  onRematch: () => void;
  onReset: () => void;
}

function outcomeText(game: Game): string {
  if (!game.winner) return "🤝 Hòa";
  return game.winner.code === game.me.faction.code ? "🎉 Bạn thắng!" : "😢 Bạn thua";
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
      <h2 id="ww-result-title">{game.winner ? `Phe ${game.winner.label} thắng!` : "Hòa — không còn ai sống"}</h2>
      <p role="status">
        <strong>{outcomeText(game)}</strong>
      </p>
      {history.games > 0 && (
        <p className="muted">
          📊 {history.games} ván · 🧑 {history.VILLAGER} · 🐺 {history.WOLF} · 👻 {history.GHOST} · 🤝 {history.draw}
        </p>
      )}
      <h3>Vai của mọi người</h3>
      <ul className="ww-reveal ww-plain-list">
        {game.players.map((p) => (
          <li key={p.id} className={p.alive ? "" : "ww-struck"}>
            <Avatar name={p.name} size={32} tone={p.faction?.code.toLowerCase()} dead={!p.alive} />
            <strong>{p.id === game.me.id ? `${p.name} ★` : p.name}</strong>
            <span>
              {p.faction ? `${FACTION_ICON[p.faction.code]} ${p.faction.label}` : ""}{" "}
              {p.ability ? `· ${abilityIcon(p.ability.code)} ${p.ability.label}` : ""}
            </span>
            <span className="sr-only">{p.alive ? "còn sống" : "đã chết"}</span>
          </li>
        ))}
      </ul>
      {room.isHost ? (
        <div className="stack">
          <button type="button" disabled={busy} onClick={onRematch}>
            🔁 Chơi lại (chia vai mới)
          </button>
          <button type="button" className="secondary" disabled={busy} onClick={onReset}>
            ↩ Về phòng chờ
          </button>
        </div>
      ) : (
        <p className="muted">Chờ chủ phòng chơi lại…</p>
      )}
    </section>
  );
}
