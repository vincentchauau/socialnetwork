"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import Alert from "./Alert";
import { NOTE, SECONDARY_BUTTON, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { DeviceSession, errorText, listSessions, revokeOtherSessions, revokeSession } from "../lib/auth";

export const SESSIONS_TITLE = "Thiết bị và phiên đăng nhập";
const MAX_RAW_UA = 60;

const METHOD_LABELS: Record<string, string> = {
  password: "Mật khẩu",
  google: "Google",
  email: "Email",
  passkey: "Passkey",
  voice: "Giọng nói",
  webcam: "Webcam (khuôn mặt)",
};

const BROWSERS: Array<[RegExp, string]> = [
  [/Edg(e|A|iOS)?\//, "Edge"],
  [/OPR\/|Opera/, "Opera"],
  [/Firefox\/|FxiOS\//, "Firefox"],
  [/Chrome\/|CriOS\//, "Chrome"],
  [/Safari\//, "Safari"],
];

const SYSTEMS: Array<[RegExp, string]> = [
  [/Windows/, "Windows"],
  [/Android/, "Android"],
  [/iPhone|iPad|iPod/, "iOS"],
  [/Mac OS X|Macintosh/, "macOS"],
  [/CrOS/, "ChromeOS"],
  [/Linux/, "Linux"],
];

const firstMatch = (table: Array<[RegExp, string]>, text: string) => table.find(([re]) => re.test(text))?.[1];

/** "Chrome trên Windows"; falls back to the trimmed raw user agent when nothing is recognised. */
export function describeDevice(userAgent: string | null): string {
  const raw = (userAgent ?? "").trim();
  if (!raw) return "Thiết bị không rõ";
  const browser = firstMatch(BROWSERS, raw);
  const system = firstMatch(SYSTEMS, raw);
  if (browser && system) return `${browser} trên ${system}`;
  if (browser || system) return (browser ?? system) as string;
  return raw.length > MAX_RAW_UA ? `${raw.slice(0, MAX_RAW_UA)}…` : raw;
}

export function formatWhen(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString("vi-VN");
}

type Loaded = { status: "loading" } | { status: "error"; text: string } | { status: "ready"; items: DeviceSession[] };

function SessionRow({ item, onRevoked }: { item: DeviceSession; onRevoked: () => Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  const { busy, error, run } = useAction();
  const device = describeDevice(item.user_agent);

  async function remove(event: FormEvent) {
    event.preventDefault();
    if (await run(async () => void (await revokeSession(item.id)))) await onRevoked();
  }

  return (
    <li className="border-t first:border-t-0 py-2 text-sm">
      <p className="font-medium">
        {device}
        {item.current && <span className="ml-2 rounded bg-green-100 px-2 py-0.5 text-xs font-normal text-green-800">Phiên này</span>}
      </p>
      <p className="text-xs text-gray-600">
        Đăng nhập bằng {METHOD_LABELS[item.method] ?? item.method} · IP {item.ip ?? "không rõ"}
      </p>
      <p className="text-xs text-gray-600">
        Bắt đầu {formatWhen(item.created_at)} · Hoạt động gần nhất {formatWhen(item.last_seen_at)}
      </p>
      {!item.current && !confirming && (
        <button type="button" className="mt-1 text-red-700 underline" onClick={() => setConfirming(true)}>
          Đăng xuất thiết bị
        </button>
      )}
      {confirming && (
        <form onSubmit={remove} aria-label={`Đăng xuất thiết bị ${device}`} className="mt-2">
          <p className={NOTE}>Đăng xuất thiết bị này?</p>
          <button type="submit" disabled={busy} className={SECONDARY_BUTTON}>{busy ? "Đang xử lý..." : "Xác nhận đăng xuất"}</button>
          <button type="button" disabled={busy} className={`${SECONDARY_BUTTON} mt-2`} onClick={() => setConfirming(false)}>Hủy</button>
        </form>
      )}
      <Alert text={error} />
    </li>
  );
}

/** Danh sách thiết bị đang đăng nhập; phiên hiện tại chỉ thoát bằng nút đăng xuất thường. */
export default function SessionsMethod() {
  const [state, setState] = useState<Loaded>({ status: "loading" });
  const others = useAction();

  const load = useCallback(async () => {
    try {
      const items = await listSessions();
      if (!Array.isArray(items)) throw new Error("Không tải được danh sách thiết bị");
      setState({ status: "ready", items });
    } catch (caught) {
      setState({ status: "error", text: errorText(caught) });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function revokeOthers() {
    let count = 0;
    if (await others.run(async () => {
      count = (await revokeOtherSessions()).revoked;
      return `Đã đăng xuất ${count} thiết bị`;
    })) await load();
  }

  const items = state.status === "ready" ? state.items : [];
  return (
    <section aria-label={SESSIONS_TITLE} className={SECTION}>
      <h2 className="font-bold mb-1">{SESSIONS_TITLE}</h2>
      <p className={NOTE}>Các thiết bị đang đăng nhập vào tài khoản của bạn.</p>
      {state.status === "loading" && <p role="status" className={NOTE}>Đang tải...</p>}
      {state.status === "error" && (
        <>
          <Alert text={state.text} />
          <button type="button" className={`${SECONDARY_BUTTON} mt-2`} onClick={() => void load()}>Thử lại</button>
        </>
      )}
      {state.status === "ready" && items.length === 0 && <p className={NOTE}>Không có phiên đăng nhập nào.</p>}
      {items.length > 0 && (
        <ul aria-label="Phiên đăng nhập đang hoạt động" className="mb-2">
          {items.map((item) => <SessionRow key={item.id} item={item} onRevoked={load} />)}
        </ul>
      )}
      {items.some((item) => !item.current) && (
        <button type="button" disabled={others.busy} className={SECONDARY_BUTTON} onClick={() => void revokeOthers()}>
          {others.busy ? "Đang xử lý..." : "Đăng xuất tất cả thiết bị khác"}
        </button>
      )}
      <Alert text={others.error} />
      <Alert text={others.message} ok />
    </section>
  );
}
