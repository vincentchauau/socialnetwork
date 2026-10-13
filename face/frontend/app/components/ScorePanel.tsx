"use client";

import { positionHint } from "../lib/geometry";
import type { PositionHint, Scores } from "../lib/types";

const POSITION_TEXT: Record<PositionHint, string> = {
  ok: "Bạn ngồi thẳng",
  tilted: "Hãy ngồi thẳng, nhìn thẳng vào camera",
  unknown: "Chưa thấy khuôn mặt",
};
const LIVE_STEP = 5;

const pct = (v: number | null) => (v === null ? "–" : `${v}%`);

/** Coarse text for the live region so screen readers are not flooded by every frame. */
export const liveSummary = (scores: Scores | null): string =>
  scores ? `Đối xứng khoảng ${Math.round(scores.symmetry / LIVE_STEP) * LIVE_STEP}%` : "Chưa thấy khuôn mặt";

export default function ScorePanel({ scores }: { scores: Scores | null }) {
  const rows: [string, string][] = [
    ["Đối xứng", scores ? pct(scores.symmetry) : "–"],
    ["Mắt", pct(scores?.eye ?? null)],
    ["Mũi", pct(scores?.nose ?? null)],
    ["Miệng", pct(scores?.mouth ?? null)],
    ["Tai", pct(scores?.ear ?? null)],
    ["Góc", scores?.angle == null ? "–" : `${scores.angle}°`],
    ["Vị trí", POSITION_TEXT[positionHint(scores?.angle ?? null)]],
  ];
  return (
    <section className="face-card" aria-labelledby="face-score-title">
      <h2 id="face-score-title">Điểm hiện tại</h2>
      <p role="status" aria-live="polite" aria-atomic="true" className="sr-only">{liveSummary(scores)}</p>
      <dl className="face-scores">
        {rows.map(([label, value]) => (
          <div key={label} className="face-score">
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="muted">Đây chỉ là ước lượng hình học, phụ thuộc ánh sáng, góc máy; không phải đánh giá sắc đẹp hay y tế.</p>
    </section>
  );
}
