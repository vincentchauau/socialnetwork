"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { werewolfApi } from "../lib/api";
import { errorText } from "../lib/errors";
import { abilityIcon, FACTION_ICON } from "../lib/theme";
import type { FactionCode, HistoryEntry } from "../lib/types";
import { tr } from "../i18n";
import { intlLocale } from "@sn/lib/i18n";

const OUTCOME = { get won() { return tr("thang"); }, get draw() { return tr("hoa_2"); }, get lost() { return tr("thua"); } } as const;
const FACTION_LABEL: Record<FactionCode, string> = { get VILLAGER() { return tr("nguoi_3"); }, get WOLF() { return tr("soi"); }, GHOST: "Ma" };

function abilityLabel(code: string): string {
  return code.toLowerCase().split("_").join(" ");
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString(intlLocale());
}

/** The caller's finished games (GET /me/history): faction, ability, outcome. */
/** The games the person played; `embedded`: shown inside another page, which has its own way back. */
export default function HistoryView({ embedded = false }: { embedded?: boolean }) {
  const [games, setGames] = useState<HistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [labels, setLabels] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    werewolfApi
      .history()
      .then(setGames)
      .catch((e: unknown) => setError(errorText(e)));
  }, []);

  useEffect(() => {
    // Ability labels come from the public rules; without them the code is shown instead.
    werewolfApi
      .meta()
      .then((meta) => setLabels(new Map(meta.abilities.map((a) => [a.code, a.label]))))
      .catch(() => undefined);
  }, []);

  const wins = games?.filter((g) => g.your_outcome === "won").length ?? 0;

  return (
    <div className="stack">
      <h1>{tr("lich_su_van_choi")}</h1>
      {!embedded && <Link href="/werewolf">{tr("quay_lai")}</Link>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {games === null && !error && <p className="muted">{tr("dang_tai")}</p>}
      {games?.length === 0 && <p className="muted">{tr("ban_chua_choi_van_nao")}</p>}
      {games && games.length > 0 && (
        <p className="muted">
          {games.length} {tr("van_gan_nhat_thang")} {wins}
        </p>
      )}
      <ul className="ww-plain-list stack">
        {games?.map((game) => (
          <li key={game.game_id} className={`card ww-history ww-outcome-${game.your_outcome}`}>
            <div className="row ww-between">
              <strong>{OUTCOME[game.your_outcome]}</strong>
              <span className="muted">{formatDate(game.finished_at)}</span>
            </div>
            <p>
              {FACTION_ICON[game.your_faction]} {FACTION_LABEL[game.your_faction]} · {abilityIcon(game.your_ability)}{" "}
              <span className="ww-ability">{labels.get(game.your_ability) ?? abilityLabel(game.your_ability)}</span>
            </p>
            <p className="muted">
              {tr("phong")} {game.room_id} · {game.size} {tr("nguoi_2")} {game.days} {tr("dem")}{" "}
              {game.survived ? tr("con_song") : tr("chet_sau_p0_dem", { p0: game.days_survived })} ·{" "}
              {game.winner === "DRAW" ? tr("hoa") : tr("phe_p0_thang", { p0: FACTION_LABEL[game.winner] })}
            </p>
            <details>
              <summary>{tr("nguoi_choi_2")}{game.players.length})</summary>
              <ul className="ww-plain-list">
                {game.players.map((p) => (
                  <li key={p.username}>
                    {p.username} {FACTION_ICON[p.faction]} {abilityIcon(p.ability)} · {OUTCOME[p.outcome]}
                    {p.survived ? "" : " · 💀"}
                  </li>
                ))}
              </ul>
            </details>
          </li>
        ))}
      </ul>
    </div>
  );
}
