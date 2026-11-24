"use client";

import { useState } from "react";

import type { HistoryState } from "../hooks/useHistory";
import { TREND_LABEL, sparklinePoints, trendOf } from "../lib/trend";
import type { Measurement } from "../lib/types";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import { intlLocale } from "@sn/lib/i18n";
import { confirmDialog } from "@sn/compounds/Dialogs";
import TextBox from "@sn/elements/TextBox";

const SPARK_W = 240;
const SPARK_H = 48;
export const CONFIRM_CLEAR = tr("xoa_toan_bo_lich_su_do");

const pct = (v: number | null) => (v === null ? "–" : `${v}%`);

export function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString(intlLocale());
}

function Sparkline({ values }: { values: number[] }) {
  const points = sparklinePoints(values, SPARK_W, SPARK_H);
  if (!points) return null;
  return (
    <svg
      className="face-spark"
      viewBox={`0 0 ${SPARK_W} ${SPARK_H}`}
      role="img"
      aria-label={tr("bieu_do_doi_xung_qua_p0", { p0: values.length })}
    >
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}

function Row({ item, onDelete, onNote }: { item: Measurement; onDelete: (id: Measurement["id"]) => void; onNote: (id: Measurement["id"], note: string) => void }) {
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <li className="face-row">
      <div>
        <strong>{tr("doi_xung")} {item.symmetry}%</strong>
        <div className="muted">
          {formatTime(item.createdAt)} {tr("mat")} {pct(item.eye)} {tr("mui")} {pct(item.nose)} {tr("mieng")} {pct(item.mouth)} · Tai {pct(item.ear)}
          {item.angle === null ? "" : tr("goc_p0", { p0: item.angle })}
        </div>
        {item.note && draft === null && <div>{item.note}</div>}
        {draft !== null && (
          <form
            className="row"
            onSubmit={(event) => {
              event.preventDefault();
              onNote(item.id, draft);
              setDraft(null);
            }}
          >
            <TextBox aria-label={tr("ghi_chu")} value={draft} maxLength={200} onChange={(event) => setDraft(event.target.value)} />
            <Button type="submit">{tr("luu")}</Button>
            <Button type="button" variant="secondary" onClick={() => setDraft(null)}>{tr("huy")}</Button>
          </form>
        )}
      </div>
      {draft === null && (
        <Button variant="secondary" type="button" onClick={() => setDraft(item.note ?? "")} aria-label={tr("ghi_chu_lan_do_luc_p0", { p0: formatTime(item.createdAt) })}>
          {tr("ghi_chu")}
        </Button>
      )}
      <Button variant="danger" type="button" className="danger" onClick={() => onDelete(item.id)} aria-label={tr("xoa_lan_do_luc_p0", { p0: formatTime(item.createdAt) })}>
        {tr("xoa")}
      </Button>
    </li>
  );
}

export default function History({ history }: { history: HistoryState }) {
  const { items, status, loadError, actionError } = history;
  const symmetries = items.map((m) => m.symmetry);

  const handleClear = async () => {
    if (await confirmDialog(CONFIRM_CLEAR)) void history.removeAll();
  };

  return (
    <section className="face-card" aria-labelledby="face-history-title">
      <div className="face-between">
        <h2 id="face-history-title">{tr("lich_su_da_luu")}</h2>
        <Button variant="danger" type="button" className="danger" onClick={handleClear} disabled={!items.length}>
          {tr("xoa_tat_ca")}
        </Button>
      </div>

      {actionError && <p role="alert" className="error">{actionError}</p>}

      {status === "loading" && <p className="muted">{tr("dang_tai_lich_su")}</p>}
      {status === "error" && (
        <div className="stack">
          <p role="alert" className="error">{loadError}</p>
          <Button type="button" onClick={() => void history.reload()}>{tr("thu_lai")}</Button>
        </div>
      )}
      {status === "ready" && !items.length && <p className="muted">{tr("chua_co_lan_do_nao_bat")}</p>}
      {status === "ready" && items.length > 0 && (
        <>
          <Sparkline values={symmetries} />
          <p className="muted">{TREND_LABEL[trendOf(symmetries)]}</p>
          <ul className="face-list">
            {items.map((item) => (
              <Row key={item.id} item={item} onDelete={(id) => void history.remove(id)} onNote={(id, note) => void history.annotate(id, note)} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
