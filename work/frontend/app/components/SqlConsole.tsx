"use client";

import { KeyboardEvent, useState } from "react";

import { errorText } from "../lib/errors";
import type { QueryResult } from "../lib/types";
import { runQuery } from "../lib/workApi";
import DataTable from "./DataTable";

export const MAX_SQL = 10000;

export default function SqlConsole({ onExecuted }: { onExecuted: () => void }) {
  const [sql, setSql] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    if (!sql.trim() || busy) return;
    setBusy(true);
    try {
      setResult(await runQuery(sql));
      setError(null);
      onExecuted();
    } catch (e) {
      setResult(null);
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      void run();
    }
  }

  return (
    <section className="stack" aria-label="Bảng điều khiển SQL">
      <h3>Bảng điều khiển SQL</h3>
      <label htmlFor="sql-input">Một câu lệnh SQL (Ctrl+Enter để chạy)</label>
      <textarea
        id="sql-input"
        rows={5}
        maxLength={MAX_SQL}
        value={sql}
        onChange={(e) => setSql(e.target.value)}
        onKeyDown={onKeyDown}
        spellCheck={false}
      />
      <div className="row">
        <button type="button" disabled={busy} onClick={() => void run()}>
          {busy ? "Đang chạy…" : "Chạy"}
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {result && (
        <div className="stack" role="status">
          <p>
            {result.rowCount} dòng, {result.changes} thay đổi.
            {result.truncated && " Kết quả đã cắt bớt."}
          </p>
          {result.truncated && <p className="muted">(đã cắt bớt: chỉ hiển thị một phần số dòng)</p>}
          <DataTable columns={result.columns} rows={result.rows} caption="Kết quả truy vấn" />
        </div>
      )}
    </section>
  );
}
