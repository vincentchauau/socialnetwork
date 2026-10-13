"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { usePolling } from "../hooks/usePolling";
import { labApi } from "../lib/api";
import { apiErrorMessage } from "../lib/errors";
import type { LogLevel, LogRow } from "../lib/types";

export const MESSAGE_MAX = 200;
export const LOGS_POLL_MS = 3000;
const LEVELS: LogLevel[] = ["info", "warn", "error"];

function LogTable({ rows }: { rows: LogRow[] }) {
  return (
    <div className="lab-scroll">
      <table className="lab-table">
        <caption>Nhật ký mới nhất</caption>
        <thead>
          <tr>
            <th scope="col">Mức</th>
            <th scope="col">Nội dung</th>
            <th scope="col">Phân vùng / vị trí</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={3} className="muted">
                Chưa có nhật ký nào.
              </td>
            </tr>
          )}
          {rows.map((row) => (
            <tr key={`${row.partition}-${row.offset}`}>
              <td>
                <span className={`lab-chip ${row.level}`}>{row.level}</span>
              </td>
              <td>{row.message}</td>
              <td>
                {row.partition} / {row.offset}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function LogsPanel({ messagingOff }: { messagingOff: boolean }) {
  const [level, setLevel] = useState<LogLevel>("info");
  const [message, setMessage] = useState("");
  const [rows, setRows] = useState<LogRow[]>([]);
  const [replay, setReplay] = useState<LogRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = usePolling(async () => {
    try {
      setRows(await labApi.logs());
      setListError(null);
    } catch (e) {
      setListError(apiErrorMessage(e));
    }
  }, LOGS_POLL_MS);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      await labApi.log(level, message);
      setNotice("Đã gửi nhật ký vào Kafka.");
      setMessage("");
      refresh();
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const runReplay = async () => {
    setError(null);
    setBusy(true);
    try {
      setReplay(await labApi.replay());
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card stack lab-wide" aria-labelledby="lab-logs-title">
      <h2 id="lab-logs-title">Luồng nhật ký (Kafka)</h2>
      <form className="stack" onSubmit={submit}>
        <div className="lab-field">
          <label htmlFor="lab-log-level">Mức</label>
          <select id="lab-log-level" value={level} onChange={(e) => setLevel(e.target.value as LogLevel)}>
            {LEVELS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <div className="lab-field">
          <label htmlFor="lab-log-message">Nội dung nhật ký</label>
          <input
            id="lab-log-message"
            value={message}
            maxLength={MESSAGE_MAX}
            onChange={(e) => setMessage(e.target.value)}
          />
          <span className="lab-counter">
            {message.length}/{MESSAGE_MAX}
          </span>
        </div>
        <div className="lab-actions">
          <button type="submit" disabled={messagingOff || busy || !message.trim()}>
            Gửi nhật ký
          </button>
          <button type="button" className="secondary" disabled={messagingOff || busy} onClick={runReplay}>
            Phát lại từ đầu
          </button>
        </div>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div role="status" aria-live="polite">
        {notice}
      </div>
      {listError && (
        <p role="alert" className="error">
          {listError}
        </p>
      )}
      <LogTable rows={rows} />
      {replay && (
        <div className="stack" role="region" aria-labelledby="lab-replay-title">
          <h3 id="lab-replay-title">Đọc lại từ đầu chủ đề (replay)</h3>
          <p className="muted">Kafka giữ tin theo thời hạn nên đọc lại được; RabbitMQ xoá tin sau khi xử lý</p>
          {replay.length === 0 && <p className="muted">Chủ đề chưa có tin nào.</p>}
          <ol className="lab-list">
            {replay.map((row) => (
              <li key={`${row.partition}-${row.offset}`}>
                [{row.level}] {row.message} ({row.partition}/{row.offset})
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
