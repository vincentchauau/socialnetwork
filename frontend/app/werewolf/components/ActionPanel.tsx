import { abilityIcon } from "../lib/theme";
import type { ActionKind, Game, GameAction } from "../lib/types";
import PlayerTile from "./PlayerTile";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";

export type PickKind = "ability" | "wolf";

interface Props {
  game: Game;
  busy: boolean;
  onPick: (target: number, kind: PickKind) => void;
}

function header(game: Game, kind: ActionKind): { icon: string; title: string; hint: string } {
  if (kind === "night") return { icon: abilityIcon(game.me.ability.code), title: game.me.ability.label, hint: tr("chon_muc_tieu") };
  if (kind === "wolf") return { icon: "🐺", title: tr("vote_giet"), hint: tr("ca_bay_chon_1_nguoi_duoc") };
  if (kind === "day") return { icon: "🗳", title: tr("treo_co_ai"), hint: tr("vote_ban_ngay_duoc_bo_trang") };
  return { icon: "🏹", title: tr("keo_theo_ai"), hint: tr("ban_vua_chet") };
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
        {action.submitted && <strong role="status">{tr("da_chon")}</strong>}
      </div>
      {action.submitted ? (
        <p>{chosen ? <>{tr("ban_chon")} <strong>{chosen.name}</strong></> : tr("ban_bo_trang")}</p>
      ) : (
        <ul className="ww-tiles ww-plain-list">
          {action.options.map((id) => {
            const player = byId.get(id);
            return player ? <PlayerTile key={id} player={player} disabled={busy} onPick={() => onPick(id, kind)} /> : null;
          })}
          {action.canAbstain && (
            <li className="ww-tile-item">
              <Button type="button" className="ww-tile ww-tile-button" disabled={busy} onClick={() => onPick(0, kind)} aria-label={tr("bo_trang")}>
                <span className="ww-avatar ww-abstain" aria-hidden="true">
                  🙈
                </span>
                <span className="ww-tile-name muted">{tr("bo_trang")}</span>
              </Button>
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
      ? tr("ban_da_chet_dang_theo_doi")
      : game.phase === "night"
        ? tr("dem_nay_ban_khong_co_hanh")
        : tr("dang_cho");
    return (
      <section className="card ww-center" aria-label={tr("hanh_dong")}>
        <p>{text}</p>
        {game.waitingFor > 0 && <p className="muted">{tr("cho")} {game.waitingFor} {tr("nguoi")}</p>}
      </section>
    );
  }
  const allDone = game.actions.every((a) => a.submitted);
  return (
    <>
      {game.actions.map((action) => (
        <ActionCard key={action.kind} game={game} action={action} busy={busy} onPick={onPick} />
      ))}
      {allDone && <p className="muted ww-center">{tr("cho")} {game.waitingFor} {tr("nguoi_con_lai")}</p>}
    </>
  );
}
