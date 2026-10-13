"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { werewolfApi } from "../lib/api";
import { errorText } from "../lib/errors";
import { abilityIcon, FACTION_ICON } from "../lib/theme";
import type { FactionCode, HistoryEntry } from "../lib/types";

const OUTCOME = { won: "🏆 Thắng", draw: "🤝 Hòa", lost: "💔 Thua" } as const;
const FACTION_LABEL: Record<FactionCode, string> = { VILLAGER: "Người", WOLF: "Sói", GHOST: "Ma" };

export function abilityLabel(code: string): string {
  return code.toLowerCase().split("_").join(" ");
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString("vi-VN");
}

/** The caller's finished games (GET /me/history): faction, ability, outcome. */
export default function HistoryView() {
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
      <h1>📜 Lịch sử ván chơi</h1>
      <Link href="/">← Quay lại</Link>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {games === null && !error && <p className="muted">Đang tải…</p>}
      {games?.length === 0 && <p className="muted">Bạn chưa chơi ván nào.</p>}
      {games && games.length > 0 && (
        <p className="muted">
          {games.length} ván gần nhất · thắng {wins}
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
              Phòng {game.room_id} · {game.size} người · {game.days} đêm ·{" "}
              {game.survived ? "còn sống" : `chết sau ${game.days_survived} đêm`} ·{" "}
              {game.winner === "DRAW" ? "hòa" : `phe ${FACTION_LABEL[game.winner]} thắng`}
            </p>
            <details>
              <summary>Người chơi ({game.players.length})</summary>
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
