"use client";

import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";

import { errorText } from "../lib/errors";
import { exportUrl } from "../lib/paths";
import type { TableInfo, TablePage } from "../lib/types";
import { getTable, importCsv, listTables, resetDatabase } from "../lib/workApi";
import SqlConsole from "./SqlConsole";

export const MAX_CSV_BYTES = 2 * 1024 * 1024;
export const SEARCH_DELAY_MS = 300;
export const MAX_PAGE_SIZE = 200;
const TABLE_NAME = /^[A-Za-z_][A-Za-z0-9_]{0,63}$/;
const PAGE_STEPS = [-100, -10, -1, 1, 10, 100];
const DEFAULT_ROWS = 3;
const DEFAULT_COLS = 2;

const clampCount = (text: string, fallback: number): number => {
  const value = Math.round(Number(text));
  return text.trim() === "" || !Number.isFinite(value) ? fallback : Math.max(1, value);
};

/** Table name from a CSV file name: "my data.csv" -> "my_data". */
export function tableNameFromFile(fileName: string): string {
  const base = fileName.replace(/\.[^.]*$/, "").replace(/[^A-Za-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
  return /^[0-9]/.test(base) ? `t_${base}` : base;
}

/** The ChatWork database manager layout: toolbar rows, header, search row and a rows x columns tile grid. */
export default function DatabasePanel() {
  const [tables, setTables] = useState<TableInfo[] | null>(null);
  const [selected, setSelected] = useState("");
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [rowsText, setRowsText] = useState(String(DEFAULT_ROWS));
  const [colsText, setColsText] = useState(String(DEFAULT_COLS));
  const [page, setPage] = useState(1);
  const [data, setData] = useState<TablePage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showSql, setShowSql] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [reloadTick, setReloadTick] = useState(0); // bumped after SQL runs so the tiles show new data
  const fileRef = useRef<HTMLInputElement>(null);

  const rows = Math.min(clampCount(rowsText, DEFAULT_ROWS), MAX_PAGE_SIZE);
  const cols = Math.min(clampCount(colsText, DEFAULT_COLS), MAX_PAGE_SIZE);
  const pageSize = Math.min(rows * cols, MAX_PAGE_SIZE);

  const refresh = useCallback(async () => {
    try {
      const list = await listTables();
      setTables(list);
      setSelected((current) => (list.some((t) => t.name === current) ? current : (list[0]?.name ?? "")));
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Debounced search; the page only resets when the query really changed (not on mount).
  const appliedQ = useRef("");
  useEffect(() => {
    const timer = setTimeout(() => {
      if (input === appliedQ.current) return;
      appliedQ.current = input;
      setQ(input);
      setPage(1);
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [input]);

  useEffect(() => {
    if (!selected) {
      setData(null);
      return;
    }
    let cancelled = false;
    getTable(selected, page, pageSize, q)
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(errorText(e));
      });
    return () => {
      cancelled = true;
    };
  }, [selected, page, pageSize, q, reloadTick]);

  const pages = data ? Math.max(1, Math.ceil(data.total / data.pageSize)) : 1;
  const goTo = (target: number) => setPage(Math.min(pages, Math.max(1, target)));

  async function importFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const table = tableNameFromFile(file.name);
    if (!TABLE_NAME.test(table)) return setError("Tên tệp phải có chữ cái hoặc số để làm tên bảng (chữ cái, số, gạch dưới; không bắt đầu bằng số).");
    if (file.size > MAX_CSV_BYTES) return setError("Tệp CSV không được lớn hơn 2 MB.");
    try {
      const done = await importCsv(table, file);
      setNotice(`Đã nhập ${done.rows} dòng vào bảng ${done.table}.`);
      setError(null);
      setSelected(done.table);
      await refresh();
    } catch (e) {
      setNotice(null);
      setError(errorText(e));
    }
  }

  async function reset() {
    try {
      await resetDatabase();
      setSelected("");
      setConfirmReset(false);
      setNotice("Đã xoá toàn bộ cơ sở dữ liệu thử.");
      await refresh();
    } catch (e) {
      setError(errorText(e));
    }
  }

  function applySearch(text: string) {
    appliedQ.current = text;
    setQ(text);
    setPage(1);
  }

  return (
    <div className="fullColumnContainer" id="databaseTable">
      <nav className="rowContainer" aria-label="Công cụ cơ sở dữ liệu">
        <button type="button" onClick={() => fileRef.current?.click()}>
          Import
        </button>
        <input ref={fileRef} type="file" hidden accept=".csv,text/csv" aria-label="Tệp CSV" onChange={(e) => void importFile(e)} />
        <button type="button" disabled={!selected} onClick={() => window.location.assign(exportUrl(selected))}>
          Export
        </button>
        <select aria-label="Bảng" value={selected} onChange={(e) => { setSelected(e.target.value); setPage(1); }}>
          {(tables ?? []).map((t) => (
            <option key={t.name} value={t.name}>
              {`${t.name} (${t.rows} dòng)`}
            </option>
          ))}
        </select>
        <button type="button" onClick={() => { setInput(""); applySearch(""); }}>
          Clear
        </button>
        <button type="button" onClick={() => applySearch(input)}>
          Search
        </button>
        <input style={{ width: 50, flex: "0 0 50px" }} type="number" min={1} aria-label="Số hàng" value={rowsText} onChange={(e) => { setRowsText(e.target.value); setPage(1); }} />
        <input style={{ width: 50, flex: "0 0 50px" }} type="number" min={1} aria-label="Số cột" value={colsText} onChange={(e) => { setColsText(e.target.value); setPage(1); }} />
        <button type="button" aria-pressed={showSql} onClick={() => setShowSql(!showSql)}>
          SQL
        </button>
        <button type="button" onClick={() => setConfirmReset(true)}>
          Reset
        </button>
      </nav>
      <nav className="rowContainer" aria-label="Phân trang">
        <button type="button" disabled={page <= 1} onClick={() => goTo(1)}>
          First
        </button>
        {PAGE_STEPS.filter((s) => s < 0).map((step) => (
          <button key={step} type="button" disabled={page <= 1} onClick={() => goTo(page + step)}>
            {step}
          </button>
        ))}
        <button type="button" onClick={() => goTo(page)}>
          {`Page ${data?.page ?? page}`}
        </button>
        {PAGE_STEPS.filter((s) => s > 0).map((step) => (
          <button key={step} type="button" disabled={page >= pages} onClick={() => goTo(page + step)}>
            {`+${step}`}
          </button>
        ))}
        <button type="button" disabled={page >= pages} onClick={() => goTo(pages)}>
          Last
        </button>
      </nav>

      {confirmReset && (
        <div className="columnContainer" role="group" aria-label="Xác nhận xoá cơ sở dữ liệu">
          <p className="text-line">Toàn bộ bảng và dữ liệu thử của bạn sẽ bị xoá vĩnh viễn. Tiếp tục?</p>
          <div className="rowContainer">
            <button type="button" onClick={() => void reset()}>
              Xác nhận xoá tất cả
            </button>
            <button type="button" onClick={() => setConfirmReset(false)}>
              Huỷ
            </button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="text-line">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-line">
          {notice}
        </p>
      )}
      <p className="status-line">
        Đây là cơ sở dữ liệu SQLite riêng của bạn, tách biệt khỏi dữ liệu của nền tảng.
        {data && ` Trang ${data.page} / ${pages} (${data.total} dòng).`}
      </p>
      {tables && tables.length === 0 && (
        <p className="text-line">Chưa có bảng nào. Hãy Import một tệp CSV hoặc chạy CREATE TABLE trong SQL.</p>
      )}

      {data && (
        <>
          <div className="rowContainer" role="row" aria-label="Tiêu đề cột">
            {data.columns.map((c, i) => (
              <div key={i} role="columnheader" style={{ flex: 1, minWidth: 100 }}>
                <b>{c}</b>
              </div>
            ))}
          </div>
          <div className="rowContainer">
            <input type="search" aria-label="Tìm kiếm" placeholder="Search..." value={input} onChange={(e) => setInput(e.target.value)} />
          </div>
          <div
            className="maxGridContainer"
            aria-label={`Dữ liệu bảng ${selected}`}
            style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}
          >
            {data.rows.length === 0 && <p className="text-line">Không có dòng nào.</p>}
            {data.rows.map((row, r) => (
              <div key={r} className="grid-item" style={{ alignItems: "stretch", textAlign: "left", overflowWrap: "anywhere" }}>
                {row.map((cell, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, padding: "2px 6px" }}>
                    <span style={{ opacity: 0.7, flex: "0 0 auto" }}>{data.columns[i]}</span>
                    <span style={{ whiteSpace: "pre-wrap" }}>{cell === null ? "NULL" : String(cell)}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </>
      )}

      {showSql && <SqlConsole onExecuted={() => { void refresh(); setReloadTick((t) => t + 1); }} />}
    </div>
  );
}
