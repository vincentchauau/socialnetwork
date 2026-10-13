"use client";

import type { HistoryState } from "../hooks/useHistory";
import { TREND_LABEL, sparklinePoints, trendOf } from "../lib/trend";
import type { Measurement } from "../lib/types";

const SPARK_W = 240;
const SPARK_H = 48;
export const CONFIRM_CLEAR = "Xoá toàn bộ lịch sử đo? Hành động này không thể hoàn tác.";

const pct = (v: number | null) => (v === null ? "–" : `${v}%`);

export function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString("vi-VN");
}

function Sparkline({ values }: { values: number[] }) {
  const points = sparklinePoints(values, SPARK_W, SPARK_H);
  if (!points) return null;
  return (
    <svg
      className="face-spark"
      viewBox={`0 0 ${SPARK_W} ${SPARK_H}`}
      role="img"
      aria-label={`Biểu đồ đối xứng qua ${values.length} lần đo, từ cũ đến mới`}
    >
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}

function Row({ item, onDelete }: { item: Measurement; onDelete: (id: Measurement["id"]) => void }) {
  return (
    <li className="face-row">
      <div>
        <strong>Đối xứng {item.symmetry}%</strong>
        <div className="muted">
          {formatTime(item.createdAt)} · Mắt {pct(item.eye)} · Mũi {pct(item.nose)} · Miệng {pct(item.mouth)} · Tai {pct(item.ear)}
          {item.angle === null ? "" : ` · Góc ${item.angle}°`}
        </div>
      </div>
      <button type="button" className="danger" onClick={() => onDelete(item.id)} aria-label={`Xoá lần đo lúc ${formatTime(item.createdAt)}`}>
        Xoá
      </button>
    </li>
  );
}

export default function History({ history }: { history: HistoryState }) {
  const { items, status, loadError, actionError } = history;
  const symmetries = items.map((m) => m.symmetry);

  const handleClear = () => {
    if (window.confirm(CONFIRM_CLEAR)) void history.removeAll();
  };

  return (
    <section className="face-card" aria-labelledby="face-history-title">
      <div className="face-between">
        <h2 id="face-history-title">Lịch sử đã lưu</h2>
        <button type="button" className="danger" onClick={handleClear} disabled={!items.length}>
          Xoá tất cả
        </button>
      </div>

      {actionError && <p role="alert" className="error">{actionError}</p>}

      {status === "loading" && <p className="muted">Đang tải lịch sử…</p>}
      {status === "error" && (
        <div className="stack">
          <p role="alert" className="error">{loadError}</p>
          <button type="button" onClick={() => void history.reload()}>Thử lại</button>
        </div>
      )}
      {status === "ready" && !items.length && <p className="muted">Chưa có lần đo nào. Bật camera và bấm “Lưu kết quả” để lưu.</p>}
      {status === "ready" && items.length > 0 && (
        <>
          <Sparkline values={symmetries} />
          <p className="muted">{TREND_LABEL[trendOf(symmetries)]}</p>
          <ul className="face-list">
            {items.map((item) => (
              <Row key={item.id} item={item} onDelete={(id) => void history.remove(id)} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
