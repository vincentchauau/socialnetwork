"use client";

import Button from "@sn/elements/Button";
import { useEffect, useState } from "react";

import { werewolfApi } from "../lib/api";
import type { LeaderEntry } from "../lib/types";
import { tr } from "../i18n";

/** The people who won most of the latest games (the first ten): their place, their name, the wins and the games they played. */
export default function Leaderboard() {
  const [board, setBoard] = useState<LeaderEntry[] | null>(null);
  const [season, setSeason] = useState<"month" | "all">("month");

  useEffect(() => {
    let cancelled = false;
    werewolfApi.leaderboard(season).then(
      (found) => !cancelled && setBoard(Array.isArray(found) ? found : []),
      () => !cancelled && setBoard([]), // the ranking is a help: no ranking is better than an error here
    );
    return () => {
      cancelled = true;
    };
  }, [season]);

  if (board === null) return null;
  return (
    <section className="card stack" aria-label={tr("ww_bang_xep_hang")}>
      <div className="row" style={{ alignItems: "center", gap: 8 }}>
        <h2 style={{ margin: 0, flex: 1 }}>🏆 {tr("ww_bang_xep_hang")}</h2>
        <Button type="button" size="sm" variant={season === "month" ? "primary" : "secondary"} aria-pressed={season === "month"} onClick={() => setSeason("month")}>{tr("ww_mua_nay")}</Button>
        <Button type="button" size="sm" variant={season === "all" ? "primary" : "secondary"} aria-pressed={season === "all"} onClick={() => setSeason("all")}>{tr("ww_tat_ca")}</Button>
      </div>
      {board.length === 0 ? <p className="muted" style={{ margin: 0 }}>{tr("ww_chua_co_ai")}</p> : null}
      <ol style={{ margin: 0, paddingLeft: 24 }}>
        {board.map((entry) => (
          <li key={entry.username}>
            <strong>{entry.username}</strong> · {tr("ww_thang_p0_tren_p1", { p0: entry.wins, p1: entry.games })}
          </li>
        ))}
      </ol>
    </section>
  );
}
