"use client";

import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";

import Alert from "@sn/elements/Alert";
import { NOTE, SECONDARY_BUTTON, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { DeviceSession, errorText, listSessions, revokeOtherSessions, revokeSession } from "../lib/auth";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import { intlLocale } from "@sn/lib/i18n";

const SESSIONS_TITLE = tr("thiet_bi_va_phien_dang_nhap");
const MAX_RAW_UA = 60;

const METHOD_LABELS: Record<string, string> = {
  get password() { return tr("mat_khau"); },
  google: "Google",
  email: "Email",
  passkey: "Passkey",
  get voice() { return tr("giong_noi"); },
  get webcam() { return tr("webcam_khuon_mat"); },
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
  if (!raw) return tr("thiet_bi_khong_ro");
  const browser = firstMatch(BROWSERS, raw);
  const system = firstMatch(SYSTEMS, raw);
  if (browser && system) return tr("browser_tren_system", { browser, system });
  if (browser || system) return (browser ?? system) as string;
  return raw.length > MAX_RAW_UA ? `${raw.slice(0, MAX_RAW_UA)}…` : raw;
}

export function formatWhen(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString(intlLocale());
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
        {item.current && <span className="ml-2 rounded bg-solid px-2 py-0.5 text-xs font-normal text-line">{tr("phien_nay")}</span>}
      </p>
      <p className="text-xs text-line">
        {tr("dang_nhap_bang")} {METHOD_LABELS[item.method] ?? item.method} · IP {item.ip ?? tr("khong_ro")}
      </p>
      <p className="text-xs text-line">
        {tr("bat_dau")} {formatWhen(item.created_at)} {tr("hoat_dong_gan_nhat")} {formatWhen(item.last_seen_at)}
      </p>
      {!item.current && !confirming && (
        <Button type="button" className="mt-1 text-line underline" onClick={() => setConfirming(true)}>
          {tr("dang_xuat_thiet_bi")}
        </Button>
      )}
      {confirming && (
        <form onSubmit={remove} aria-label={tr("dang_xuat_thiet_bi_device", { device })} className="mt-2">
          <p className={NOTE}>{tr("dang_xuat_thiet_bi_nay")}</p>
          <Button variant="secondary" type="submit" disabled={busy} className={SECONDARY_BUTTON}>{busy ? tr("dang_xu_ly") : tr("xac_nhan_dang_xuat")}</Button>
          <Button variant="secondary" type="button" disabled={busy} className={`${SECONDARY_BUTTON} mt-2`} onClick={() => setConfirming(false)}>{tr("huy")}</Button>
        </form>
      )}
      <Alert className="mt-2">{error}</Alert>
    </li>
  );
}

/** Danh sách thiết bị đang đăng nhập; phiên hiện tại chỉ thoát bằng nút đăng xuất thường. */
/** The devices signed in to the account; `children` (a button, say) go at the bottom of the same card. */
export default function SessionsMethod({ children }: { children?: ReactNode }) {
  const [state, setState] = useState<Loaded>({ status: "loading" });
  const others = useAction();

  const load = useCallback(async () => {
    try {
      const items = await listSessions();
      if (!Array.isArray(items)) throw new Error(tr("khong_tai_duoc_danh_sach_thiet"));
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
      return tr("da_dang_xuat_count_thiet_bi", { count });
    })) await load();
  }

  const items = state.status === "ready" ? state.items : [];
  return (
    <section aria-label={SESSIONS_TITLE} className={SECTION}>
      <h2 className="font-bold mb-1">{SESSIONS_TITLE}</h2>
      <p className={NOTE}>{tr("cac_thiet_bi_dang_dang_nhap")}</p>
      {state.status === "loading" && <p role="status" className={NOTE}>{tr("dang_tai")}</p>}
      {state.status === "error" && (
        <>
          <Alert className="mt-2">{state.text}</Alert>
          <Button variant="secondary" type="button" className={`${SECONDARY_BUTTON} mt-2`} onClick={() => void load()}>{tr("thu_lai")}</Button>
        </>
      )}
      {state.status === "ready" && items.length === 0 && <p className={NOTE}>{tr("khong_co_phien_dang_nhap_nao")}</p>}
      {items.length > 0 && (
        <ul aria-label={tr("phien_dang_nhap_dang_hoat_dong")} className="mb-2">
          {items.map((item) => <SessionRow key={item.id} item={item} onRevoked={load} />)}
        </ul>
      )}
      {items.some((item) => !item.current) && (
        <Button variant="secondary" type="button" disabled={others.busy} className={SECONDARY_BUTTON} onClick={() => void revokeOthers()}>
          {others.busy ? tr("dang_xu_ly") : tr("dang_xuat_tat_ca_thiet_bi")}
        </Button>
      )}
      {children}
      <Alert className="mt-2">{others.error}</Alert>
      <Alert tone="success" className="mt-2">{others.message}</Alert>
    </section>
  );
}
