import { abilityIcon } from "../lib/theme";
import type { ActionKind, Game, GameAction } from "../lib/types";
import PlayerTile from "./PlayerTile";

export type PickKind = "ability" | "wolf";

interface Props {
  game: Game;
  busy: boolean;
  onPick: (target: number, kind: PickKind) => void;
}

function header(game: Game, kind: ActionKind): { icon: string; title: string; hint: string } {
  if (kind === "night") return { icon: abilityIcon(game.me.ability.code), title: game.me.ability.label, hint: "Chọn mục tiêu" };
  if (kind === "wolf") return { icon: "🐺", title: "Vote giết", hint: "Cả bầy chọn 1 người (được bỏ trắng)" };
  if (kind === "day") return { icon: "🗳", title: "Treo cổ ai?", hint: "Vote ban ngày (được bỏ trắng)" };
  return { icon: "🏹", title: "Kéo theo ai?", hint: "Bạn vừa chết" };
}

function ActionCard({ game, action, busy, onPick }: Props & { action: GameAction }) {
  const head = header(game, action.kind);
  const byId = new Map(game.players.map((p) => [p.id, p]));
  const kind: PickKind = action.kind === "wolf" ? "wolf" : "ability";
  const chosen = action.current ? byId.get(action.current) : undefined;
  const titleId = `ww-action-${action.kind}`;

  return (
    <section className={`card ww-action${action.submitted ? " ww-done" : ""}`} aria-labelledby={titleId}>
      <div className="row ww-between">
        <div>
          <h2 id={titleId}>
            <span aria-hidden="true">{head.icon}</span> {head.title}
          </h2>
          <p className="muted">{head.hint}</p>
        </div>
        {action.submitted && <strong role="status">✔ Đã chọn</strong>}
      </div>
      {action.submitted ? (
        <p>{chosen ? <>Bạn chọn: <strong>{chosen.name}</strong></> : "Bạn bỏ trắng."}</p>
      ) : (
        <ul className="ww-tiles ww-plain-list">
          {action.options.map((id) => {
            const player = byId.get(id);
            return player ? <PlayerTile key={id} player={player} disabled={busy} onPick={() => onPick(id, kind)} /> : null;
          })}
          {action.canAbstain && (
            <li className="ww-tile-item">
              <button type="button" className="ww-tile ww-tile-button" disabled={busy} onClick={() => onPick(0, kind)} aria-label="Bỏ trắng">
                <span className="ww-avatar ww-abstain" aria-hidden="true">
                  🙈
                </span>
                <span className="ww-tile-name muted">Bỏ trắng</span>
              </button>
            </li>
          )}
        </ul>
      )}
    </section>
  );
}

/** What you may do now: one card per action (wolves get two at night: ability and the kill vote). */
export default function ActionPanel({ game, busy, onPick }: Props) {
  if (game.actions.length === 0) {
    const text = !game.me.alive
      ? "👻 Bạn đã chết, đang theo dõi"
      : game.phase === "night"
        ? "😴 Đêm nay bạn không có hành động"
        : "⏳ Đang chờ…";
    return (
      <section className="card ww-center" aria-label="Hành động">
        <p>{text}</p>
        {game.waitingFor > 0 && <p className="muted">⏳ Chờ {game.waitingFor} người</p>}
      </section>
    );
  }
  const allDone = game.actions.every((a) => a.submitted);
  return (
    <>
      {game.actions.map((action) => (
        <ActionCard key={action.kind} game={game} action={action} busy={busy} onPick={onPick} />
      ))}
      {allDone && <p className="muted ww-center">⏳ Chờ {game.waitingFor} người còn lại</p>}
    </>
  );
}
