"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { usePolling } from "../hooks/usePolling";
import { labApi } from "../lib/api";
import { apiErrorMessage } from "../lib/errors";
import type { JobStatus, NotificationRow } from "../lib/types";

export const TITLE_MAX = 80;
export const BODY_MAX = 300;
export const FAST_POLL_MS = 2000;
export const SLOW_POLL_MS = 10000;
export const FAIL_TITLE = "[fail] Tin thử lỗi";
export const FAIL_BODY = "Tin này cố ý bị lỗi để xem thử lại và hàng đợi tin lỗi.";

const ACTIVE: JobStatus[] = ["queued", "processing", "retrying"];

export default function QueuePanel({ messagingOff }: { messagingOff: boolean }) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [rows, setRows] = useState<NotificationRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const hasActive = rows.some((row) => ACTIVE.includes(row.status));
  const refresh = usePolling(async () => {
    try {
      setRows(await labApi.notifications());
      setListError(null);
    } catch (e) {
      setListError(apiErrorMessage(e));
    }
  }, hasActive ? FAST_POLL_MS : SLOW_POLL_MS);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const created = await labApi.notify(title, body);
      setNotice(`Đã gửi vào hàng đợi (mã ${created.id}).`);
      setTitle("");
      setBody("");
      refresh();
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const fillFail = () => {
    setTitle(FAIL_TITLE);
    setBody(FAIL_BODY);
  };

  return (
    <section className="card stack lab-wide" aria-labelledby="lab-queue-title">
      <h2 id="lab-queue-title">Hàng đợi thông báo (RabbitMQ)</h2>
      <form className="stack" onSubmit={submit}>
        <div className="lab-field">
          <label htmlFor="lab-notify-title">Tiêu đề</label>
          <input id="lab-notify-title" value={title} maxLength={TITLE_MAX} onChange={(e) => setTitle(e.target.value)} />
          <span className="lab-counter">
            {title.length}/{TITLE_MAX}
          </span>
        </div>
        <div className="lab-field">
          <label htmlFor="lab-notify-body">Nội dung thông báo</label>
          <textarea
            id="lab-notify-body"
            rows={3}
            value={body}
            maxLength={BODY_MAX}
            onChange={(e) => setBody(e.target.value)}
          />
          <span className="lab-counter">
            {body.length}/{BODY_MAX}
          </span>
        </div>
        <p className="muted">Tiêu đề bắt đầu bằng [fail] để thấy thử lại và hàng đợi tin lỗi (DLQ)</p>
        <div className="lab-actions">
          <button type="submit" disabled={messagingOff || busy || !title.trim()}>
            Gửi
          </button>
          <button type="button" className="secondary" onClick={fillFail}>
            Gửi thử tin lỗi
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
      <div className="lab-scroll">
        <table className="lab-table">
          <caption>Thông báo gần đây</caption>
          <thead>
            <tr>
              <th scope="col">Tiêu đề</th>
              <th scope="col">Trạng thái</th>
              <th scope="col">Số lần thử</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={3} className="muted">
                  Chưa có thông báo nào.
                </td>
              </tr>
            )}
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.title}</td>
                <td>
                  <span className={`lab-chip ${row.status}`}>{row.status}</span>
                </td>
                <td>{row.attempts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
