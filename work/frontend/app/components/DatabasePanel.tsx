"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { errorText } from "../lib/errors";
import { exportUrl } from "../lib/paths";
import type { TableInfo } from "../lib/types";
import { importCsv, listTables, resetDatabase } from "../lib/workApi";
import SqlConsole from "./SqlConsole";
import TableViewer from "./TableViewer";

export const MAX_CSV_BYTES = 2 * 1024 * 1024;
const TABLE_NAME = /^[A-Za-z_][A-Za-z0-9_]{0,63}$/;

export default function DatabasePanel() {
  const [tables, setTables] = useState<TableInfo[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [tableName, setTableName] = useState("");
  const [confirmReset, setConfirmReset] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      setTables(await listTables());
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function submitImport(event: FormEvent) {
    event.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!TABLE_NAME.test(tableName)) return setError("Tên bảng chỉ gồm chữ cái, số, dấu gạch dưới và không bắt đầu bằng số.");
    if (!file) return setError("Hãy chọn tệp CSV.");
    if (file.size > MAX_CSV_BYTES) return setError("Tệp CSV không được lớn hơn 2 MB.");
    try {
      const done = await importCsv(tableName, file);
      setNotice(`Đã nhập ${done.rows} dòng vào bảng ${done.table}.`);
      setTableName("");
      if (fileRef.current) fileRef.current.value = "";
      await refresh();
    } catch (e) {
      setNotice(null);
      setError(errorText(e));
    }
  }

  async function reset() {
    try {
      await resetDatabase();
      setSelected(null);
      setConfirmReset(false);
      setNotice("Đã xoá toàn bộ cơ sở dữ liệu thử.");
      await refresh();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <div className="stack">
      <p className="card">Đây là cơ sở dữ liệu SQLite riêng của bạn, tách biệt khỏi dữ liệu của nền tảng.</p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}

      <section className="stack" aria-label="Danh sách bảng">
        <h3>Các bảng</h3>
        {!tables && !error && <p className="muted">Đang tải…</p>}
        {tables && tables.length === 0 && <p className="muted">Chưa có bảng nào. Hãy nhập CSV hoặc chạy CREATE TABLE.</p>}
        {tables && tables.length > 0 && (
          <ul className="tables">
            {tables.map((t) => (
              <li key={t.name} className="row">
                <button
                  type="button"
                  className={selected === t.name ? undefined : "secondary"}
                  aria-pressed={selected === t.name}
                  onClick={() => setSelected(t.name)}
                >
                  {t.name} ({t.rows} dòng)
                </button>
                <a className="btn secondary" href={exportUrl(t.name)} download aria-label={`Xuất CSV bảng ${t.name}`}>
                  Xuất CSV
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>

      {selected && <TableViewer name={selected} />}

      <SqlConsole onExecuted={() => void refresh()} />

      <form className="card stack" onSubmit={submitImport} aria-label="Nhập CSV">
        <h3>Nhập CSV (tối đa 2 MB)</h3>
        <label htmlFor="import-table">Tên bảng</label>
        <input id="import-table" value={tableName} maxLength={64} onChange={(e) => setTableName(e.target.value)} />
        <label htmlFor="import-file">Tệp CSV</label>
        <input id="import-file" ref={fileRef} type="file" accept=".csv,text/csv" />
        <button type="submit">Nhập</button>
      </form>

      {!confirmReset ? (
        <button type="button" className="danger" onClick={() => setConfirmReset(true)}>
          Xoá toàn bộ cơ sở dữ liệu thử
        </button>
      ) : (
        <div className="card stack" role="group" aria-label="Xác nhận xoá cơ sở dữ liệu">
          <p>Toàn bộ bảng và dữ liệu thử của bạn sẽ bị xoá vĩnh viễn. Tiếp tục?</p>
          <div className="row">
            <button type="button" className="danger" onClick={() => void reset()}>
              Xác nhận xoá tất cả
            </button>
            <button type="button" className="secondary" onClick={() => setConfirmReset(false)}>
              Huỷ
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
