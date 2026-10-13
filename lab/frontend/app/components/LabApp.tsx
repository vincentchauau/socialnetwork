"use client";

import { useState } from "react";

import { usePolling } from "../hooks/usePolling";
import { labApi } from "../lib/api";
import { apiErrorMessage } from "../lib/errors";
import type { LabStatus } from "../lib/types";
import GuideSection from "./GuideSection";
import LogsPanel from "./LogsPanel";
import LookupPanel from "./LookupPanel";
import QueuePanel from "./QueuePanel";
import StatusBar from "./StatusBar";

export const STATUS_POLL_MS = 5000;
export const CONFIRM_CLEAR_EVENTS = "Xoá toàn bộ dữ liệu thử (thông báo và nhật ký) của bạn?";

export default function LabApp() {
  const [status, setStatus] = useState<LabStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  usePolling(async () => {
    try {
      setStatus(await labApi.status());
      setStatusError(null);
    } catch (e) {
      setStatusError(apiErrorMessage(e));
    }
  }, STATUS_POLL_MS);

  const clearEvents = async () => {
    if (!window.confirm(CONFIRM_CLEAR_EVENTS)) return;
    setNotice(null);
    setError(null);
    try {
      await labApi.clearEvents();
      setNotice("Đã xoá dữ liệu thử của bạn.");
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const messagingOff = status?.messaging === false;

  return (
    <div className="stack">
      <h1>Phòng thí nghiệm</h1>
      <p className="muted">Sân chơi nhỏ để xem gRPC, Redis, RabbitMQ và Kafka hoạt động thế nào.</p>
      <StatusBar status={status} error={statusError} />
      <div className="lab-panels">
        <LookupPanel />
        <QueuePanel messagingOff={messagingOff} />
        <LogsPanel messagingOff={messagingOff} />
      </div>
      <GuideSection />
      <div className="lab-actions">
        <button type="button" className="danger" onClick={clearEvents}>
          Xoá dữ liệu thử của tôi
        </button>
        <a href="/">← Trang chủ</a>
      </div>
      <div role="status" aria-live="polite">
        {notice}
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  );
}
