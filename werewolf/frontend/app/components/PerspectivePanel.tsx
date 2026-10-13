"use client";

import { useEffect, useState } from "react";

import { werewolfApi } from "../lib/api";
import { errorText } from "../lib/errors";
import { abilityIcon, FACTION_ICON } from "../lib/theme";
import type { Game } from "../lib/types";
import EventLog from "./EventLog";

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

  if (!mayPeek) return <EventLog title="Nhật ký của bạn" log={game.log} />;

  const chosen = selected === ALL ? null : game.players.find((p) => p.id === selected);
  const known = view?.players.filter((p) => p.id !== selected && (p.faction || p.ability)) ?? [];

  return (
    <>
      <section className="card" aria-label="Xem nhật ký theo">
        <h2>🔍 Xem nhật ký theo</h2>
        <div className="ww-chips" role="group" aria-label="Góc nhìn">
          <button type="button" className={`ww-chip ${selected === ALL ? "" : "secondary"}`} aria-pressed={selected === ALL} onClick={() => setSelected(ALL)}>
            🌐 Toàn bộ
          </button>
          {game.players.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`ww-chip ${selected === p.id ? "" : "secondary"}`}
              aria-pressed={selected === p.id}
              onClick={() => setSelected(p.id)}
            >
              {p.alive ? "" : "💀 "}
              {p.name}
            </button>
          ))}
        </div>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
      </section>
      {view && chosen && (
        <section className="card" aria-label={`Góc nhìn của ${chosen.name}`}>
          <h2>👁️ Góc nhìn của {chosen.name}</h2>
          <p>
            {FACTION_ICON[view.me.faction.code]} {view.me.faction.label} · {abilityIcon(view.me.ability.code)} {view.me.ability.label}
            {view.me.alive ? "" : " · 💀 Đã chết"}
          </p>
          <p className="muted">👀 {chosen.name} đã biết:</p>
          {known.length === 0 && <p className="muted">Chưa biết thêm ai.</p>}
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
      <EventLog title={chosen ? `Nhật ký — ${chosen.name} thấy` : "Nhật ký đầy đủ"} log={chosen ? (view?.log ?? []) : game.log} />
    </>
  );
}
