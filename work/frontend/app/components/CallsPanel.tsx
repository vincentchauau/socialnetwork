"use client";

import { useEffect, useState } from "react";

import { errorText } from "../lib/errors";
import type { CallEvent } from "../lib/types";
import { listCalls } from "../lib/workApi";

export default function CallsPanel() {
  const [calls, setCalls] = useState<CallEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCalls(50)
      .then(setCalls)
      .catch((e) => setError(errorText(e)));
  }, []);

  if (error) {
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  }
  if (!calls) {
    return (
      <p className="muted" role="status">
        Đang tải…
      </p>
    );
  }
  if (calls.length === 0) return <p className="muted">Chưa có cuộc gọi nào.</p>;
  return (
    <div className="table-wrap">
      <table>
        <caption className="muted">Sự kiện cuộc gọi gần đây (số điện thoại đã được che)</caption>
        <thead>
          <tr>
            <th scope="col">Thời gian</th>
            <th scope="col">Sự kiện</th>
            <th scope="col">Từ</th>
            <th scope="col">Đến</th>
          </tr>
        </thead>
        <tbody>
          {calls.map((c) => (
            <tr key={c.id}>
              <td>{c.createdAt}</td>
              <td>{c.eventType}</td>
              <td>{c.fromNumber}</td>
              <td>{c.toNumber}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
