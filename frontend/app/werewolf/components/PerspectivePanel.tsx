"use client";

import { useEffect, useState } from "react";

import { werewolfApi } from "../lib/api";
import { errorText } from "../lib/errors";
import { abilityIcon, FACTION_ICON } from "../lib/theme";
import type { Game } from "../lib/types";
import EventLog from "./EventLog";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";

const ALL = 0;

/**
 * The log, and other players' perspectives. Contract: a living player only has their own log; the full log and
 * other perspectives exist only for the dead and once the game is over, so the picker is not rendered otherwise.
 */
export default function PerspectivePanel({ code, game }: { code: string; game: Game }) {
  const mayPeek = !game.me.alive || game.gameOver;
  const [selected, setSelected] = useState(ALL);
  const [view, setView] = useState<Game | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!mayPeek || selected === ALL) {
      setView(null);
      setError(null);
      return undefined;
    }
    let cancelled = false;
    werewolfApi
      .perspective(code, selected)
      .then((value) => {
        if (cancelled) return;
        setView(value);
        setError(null);
      })
      .catch((e: unknown) => !cancelled && setError(errorText(e)));
    return () => {
      cancelled = true;
    };
  }, [mayPeek, selected, code, game.log.length, game.phase, game.night]);

  if (!mayPeek) return <EventLog title={tr("nhat_ky_cua_ban")} log={game.log} />;

  const chosen = selected === ALL ? null : game.players.find((p) => p.id === selected);
  const known = view?.players.filter((p) => p.id !== selected && (p.faction || p.ability)) ?? [];

  return (
    <>
      <section className="card" aria-label={tr("xem_nhat_ky_theo")}>
        <h2>{tr("xem_nhat_ky_theo_2")}</h2>
        <div className="ww-chips" role="group" aria-label={tr("goc_nhin")}>
          <Button variant="secondary" type="button" className={`ww-chip ${selected === ALL ? "" : "secondary"}`} aria-pressed={selected === ALL} onClick={() => setSelected(ALL)}>
            {tr("toan_bo")}
          </Button>
          {game.players.map((p) => (
            <Button variant="secondary"
              key={p.id}
              type="button"
              className={`ww-chip ${selected === p.id ? "" : "secondary"}`}
              aria-pressed={selected === p.id}
              onClick={() => setSelected(p.id)}
            >
              {p.alive ? "" : "💀 "}
              {p.name}
            </Button>
          ))}
        </div>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
      </section>
      {view && chosen && (
        <section className="card" aria-label={tr("goc_nhin_cua_p0", { p0: chosen.name })}>
          <h2>{tr("goc_nhin_cua")} {chosen.name}</h2>
          <p>
            {FACTION_ICON[view.me.faction.code]} {view.me.faction.label} · {abilityIcon(view.me.ability.code)} {view.me.ability.label}
            {view.me.alive ? "" : tr("da_chet")}
          </p>
          <p className="muted">👀 {chosen.name} {tr("da_biet")}</p>
          {known.length === 0 && <p className="muted">{tr("chua_biet_them_ai")}</p>}
          <ul className="ww-plain-list">
            {known.map((p) => (
              <li key={p.id}>
                {p.name} {p.faction ? `${FACTION_ICON[p.faction.code]} ${p.faction.label}` : ""}{" "}
                {p.ability ? `${abilityIcon(p.ability.code)} ${p.ability.label}` : ""}
              </li>
            ))}
          </ul>
        </section>
      )}
      <EventLog title={chosen ? tr("nhat_ky_p0_thay", { p0: chosen.name }) : tr("nhat_ky_day_du")} log={chosen ? (view?.log ?? []) : game.log} />
    </>
  );
}
