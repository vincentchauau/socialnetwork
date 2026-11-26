"use client";

import { useEffect, useState } from "react";

import RankingList from "@sn/compounds/RankingList";
import Select from "@sn/elements/Select";

import { werewolfApi } from "../lib/api";
import type { LeaderEntry } from "../lib/types";
import { tr } from "../i18n";

type Season = "month" | "all";

/** The ranking of the Werewolf: who won most of the latest games, this month or all the time. */
export default function Leaderboard() {
  const [season, setSeason] = useState<Season>("month");
  const [rows, setRows] = useState<LeaderEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setRows(null);
    setError(null);
    werewolfApi
      .leaderboard(season)
      .then((list) => { if (alive) setRows(list); })
      .catch(() => { if (alive) setError(tr("ww_ranking_error")); });
    return () => { alive = false; };
  }, [season]);

  return (
    <section className="card stack" aria-labelledby="ww-leaderboard-title">
      <div className="row">
        <h2 id="ww-leaderboard-title">{tr("ww_bang_xep_hang")}</h2>
        <Select aria-label={tr("ww_bang_xep_hang")} value={season} onChange={(event) => setSeason(event.target.value as Season)}>
          <option value="month">{tr("ww_this_month")}</option>
          <option value="all">{tr("ww_all_time")}</option>
        </Select>
      </div>
      {error ? (
        <p role="alert" className="error">{error}</p>
      ) : rows === null ? (
        <p role="status" className="muted">{tr("ww_loading")}</p>
      ) : rows.length === 0 ? (
        <p className="muted">{tr("ww_no_ranking")}</p>
      ) : (
        <RankingList
          className="ww-ranking"
          valueClass="muted"
          rows={rows.map((row) => ({ key: row.username, name: row.username, value: tr("ww_thang_p0_tren_p1", { p0: row.wins, p1: row.games }) }))}
        />
      )}
    </section>
  );
}
