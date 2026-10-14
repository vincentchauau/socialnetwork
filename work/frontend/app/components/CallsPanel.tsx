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
      <p role="alert" className="text-line">
        {error}
      </p>
    );
  }
  if (!calls) {
    return (
      <p className="text-line" role="status">
        Đang tải…
      </p>
    );
  }
  if (calls.length === 0) return <p className="text-line">Chưa có cuộc gọi nào.</p>;
  return (
    <div style={{ overflow: "auto" }}>
      <table>
        <caption className="text-line">Sự kiện cuộc gọi gần đây (số điện thoại đã được che)</caption>
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
