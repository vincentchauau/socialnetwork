"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { labApi } from "../lib/api";
import { apiErrorMessage } from "../lib/errors";
import type { UserLookup } from "../lib/types";

export const ID_PATTERN = /^[0-9A-Za-z]{1,16}$/;
export const HISTORY_SIZE = 5;
export const INVALID_ID = "Mã người dùng gồm 1–16 ký tự chữ hoặc số.";

export const sourceLabel = (source: UserLookup["source"]) =>
  source === "cache" ? "Từ cache Redis" : "Từ gRPC";

export default function LookupPanel() {
  const [id, setId] = useState("1");
  const [result, setResult] = useState<UserLookup | null>(null);
  const [history, setHistory] = useState<UserLookup[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const guarded = async (action: () => Promise<void>) => {
    setNotice(null);
    if (!ID_PATTERN.test(id)) {
      setError(INVALID_ID);
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await action();
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const lookup = (event: FormEvent) => {
    event.preventDefault();
    return guarded(async () => {
      const found = await labApi.lookup(id);
      setResult(found);
      setHistory((old) => [found, ...old].slice(0, HISTORY_SIZE));
    });
  };

  const clearCache = () =>
    guarded(async () => {
      await labApi.clearCache(id);
      setNotice(`Đã xoá cache của người dùng ${id}. Lần tra tới sẽ đi qua gRPC.`);
    });

  return (
    <section className="card stack" aria-labelledby="lab-lookup-title">
      <h2 id="lab-lookup-title">Tra người dùng (gRPC + cache Redis)</h2>
      <p className="muted">
        Cache-aside: hỏi cache trước, có thì trả ngay. Không có thì gọi gRPC lấy dữ liệu rồi ghi vào cache cho lần sau.
      </p>
      <form className="stack" onSubmit={lookup}>
        <div className="lab-field">
          <label htmlFor="lab-user-id">Mã người dùng</label>
          <input id="lab-user-id" value={id} maxLength={16} onChange={(e) => setId(e.target.value)} />
        </div>
        <div className="lab-actions">
          <button type="submit" disabled={busy}>
            Tra
          </button>
          <button type="button" className="secondary" disabled={busy} onClick={clearCache}>
            Xoá cache
          </button>
        </div>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div role="status" aria-live="polite" className="stack">
        {notice && <p>{notice}</p>}
        {result && (
          <p>
            <strong>{result.name}</strong>{" "}
            <span className={`lab-chip ${result.source}`}>{sourceLabel(result.source)}</span>{" "}
            <span>{result.ms} ms</span>
          </p>
        )}
      </div>
      {history.length > 0 && (
        <div className="lab-scroll">
          <table className="lab-table">
            <caption>5 lần tra gần nhất</caption>
            <thead>
              <tr>
                <th scope="col">Mã</th>
                <th scope="col">Tên</th>
                <th scope="col">Nguồn</th>
                <th scope="col">Thời gian</th>
              </tr>
            </thead>
            <tbody>
              {history.map((row, i) => (
                <tr key={i}>
                  <td>{row.id}</td>
                  <td>{row.name}</td>
                  <td>{sourceLabel(row.source)}</td>
                  <td>{row.ms} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
