"use client";

import { positionHint } from "../lib/geometry";
import type { PositionHint, Scores } from "../lib/types";
import { tr } from "../i18n";

const POSITION_TEXT: Record<PositionHint, string> = {
  get ok() { return tr("ban_ngoi_thang"); },
  get tilted() { return tr("hay_ngoi_thang_nhin_thang_vao"); },
  get unknown() { return tr("chua_thay_khuon_mat"); },
};
const LIVE_STEP = 5;

const pct = (v: number | null) => (v === null ? "–" : `${v}%`);

/** Coarse text for the live region so screen readers are not flooded by every frame. */
export const liveSummary = (scores: Scores | null): string =>
  scores ? tr("doi_xung_khoang_p0", { p0: Math.round(scores.symmetry / LIVE_STEP) * LIVE_STEP }) : tr("chua_thay_khuon_mat");

export default function ScorePanel({ scores }: { scores: Scores | null }) {
  const rows: [string, string][] = [
    [tr("doi_xung"), scores ? pct(scores.symmetry) : "–"],
    [tr("mat_2"), pct(scores?.eye ?? null)],
    [tr("mui_2"), pct(scores?.nose ?? null)],
    [tr("mieng_2"), pct(scores?.mouth ?? null)],
    ["Tai", pct(scores?.ear ?? null)],
    [tr("goc"), scores?.angle == null ? "–" : `${scores.angle}°`],
    [tr("vi_tri"), POSITION_TEXT[positionHint(scores?.angle ?? null)]],
  ];
  return (
    <section className="face-card" aria-labelledby="face-score-title">
      <h2 id="face-score-title">{tr("diem_hien_tai")}</h2>
      <p role="status" aria-live="polite" aria-atomic="true" className="sr-only">{liveSummary(scores)}</p>
      <dl className="face-scores">
        {rows.map(([label, value]) => (
          <div key={label} className="face-score">
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="muted">{tr("day_chi_la_uoc_luong_hinh")}</p>
    </section>
  );
}
