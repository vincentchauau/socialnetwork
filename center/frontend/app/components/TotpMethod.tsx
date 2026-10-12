"use client";

import QRCode from "qrcode";
import { FormEvent, useEffect, useState } from "react";

import Alert from "./Alert";
import RecoveryCodesBox, { CopyButton } from "./RecoveryCodesBox";
import { digitsOnly, TOTP_LENGTH } from "./TotpLoginForm";
import { INPUT, LABEL, NOTE, PRIMARY_BUTTON, SECONDARY_BUTTON, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { TotpSetup, totpDisable, totpEnable, totpRegenerateRecoveryCodes, totpSetup } from "../lib/auth";

export const TOTP_TITLE = "Xác thực hai bước (TOTP)";
export const TOTP_HINT = "Mã này chỉ dùng làm bước thứ hai sau khi đăng nhập";
export const LOW_CODES_THRESHOLD = 2;

interface Props {
  enabled: boolean;
  recoveryCodesLeft: number;
  hasPassword: boolean;
  onDone: () => void | Promise<void>;
}

type Done = Props["onDone"];

/** The QR is drawn in the browser: the secret never goes to a third-party service. */
function QrImage({ uri }: { uri: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    QRCode.toString(uri, { type: "svg", margin: 1, width: 192 })
      .then((svg) => !cancelled && setSrc(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [uri]);

  if (failed) return <p role="note" className="text-sm text-red-600 mb-2">Không tạo được mã QR, hãy nhập khóa bên dưới thủ công.</p>;
  if (!src) return null;
  return <img src={src} alt="Mã QR để thêm tài khoản vào ứng dụng xác thực" width={192} height={192} className="mx-auto mb-2 border" />;
}

function PasswordInput({ id, value, onChange }: { id: string; value: string; onChange: (value: string) => void }) {
  return (
    <>
      <label htmlFor={id} className={LABEL}>Nhập lại mật khẩu để xác nhận</label>
      <input id={id} type="password" value={value} autoComplete="current-password" required
             onChange={(e) => onChange(e.target.value)} className={INPUT} />
    </>
  );
}

/** Tắt: chưa bật thì hỏi mật khẩu (nếu có) rồi lấy khóa thiết lập. */
function StartSetup({ hasPassword, onStarted }: { hasPassword: boolean; onStarted: (setup: TotpSetup, password?: string) => void }) {
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent) {
    event.preventDefault();
    let started: TotpSetup | undefined;
    const sent = hasPassword ? password : undefined;
    const ok = await run(async () => void (started = await totpSetup(sent)));
    setPassword("");
    if (ok && started) onStarted(started, sent);
  }

  return (
    <form onSubmit={submit} aria-label="Bật xác thực hai bước">
      <p className={NOTE}>Dùng ứng dụng như Google Authenticator hoặc Authy để tạo mã 6 chữ số.</p>
      {hasPassword && <PasswordInput id="totp-start-password" value={password} onChange={setPassword} />}
      <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>{busy ? "Đang xử lý..." : "Bật"}</button>
      <Alert text={error} />
    </form>
  );
}

/** QR + khóa để nhập tay + ô nhập mã đầu tiên để xác nhận. */
function ConfirmSetup({ setup, password, onEnabled, onCancel }: { setup: TotpSetup; password?: string; onEnabled: (codes: string[]) => void; onCancel: () => void }) {
  const [code, setCode] = useState("");
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent) {
    event.preventDefault();
    let codes: string[] = [];
    if (await run(async () => void (codes = (await totpEnable(code, password)).recovery_codes))) onEnabled(codes);
    else setCode("");
  }

  return (
    <form onSubmit={submit} aria-label="Xác nhận mã xác thực">
      <p className={NOTE}>Quét mã QR bằng ứng dụng xác thực, rồi nhập mã 6 chữ số hiện ra để hoàn tất.</p>
      <QrImage uri={setup.otpauth_uri} />
      <p className="text-sm mb-1">Hoặc nhập khóa này thủ công:</p>
      <p className="font-mono text-sm break-all mb-1" aria-label="Khóa thiết lập">{setup.secret}</p>
      <div className="mb-2"><CopyButton text={setup.secret} label="Sao chép khóa" /></div>
      <label htmlFor="totp-confirm-code" className={LABEL}>Mã xác thực 6 chữ số</label>
      <input id="totp-confirm-code" value={code} inputMode="numeric" autoComplete="one-time-code" maxLength={TOTP_LENGTH}
             disabled={busy} onChange={(e) => setCode(digitsOnly(e.target.value))} className={INPUT} />
      <button type="submit" disabled={busy || code.length !== TOTP_LENGTH} className={PRIMARY_BUTTON}>
        {busy ? "Đang xử lý..." : "Xác nhận và bật"}
      </button>
      <button type="button" disabled={busy} onClick={onCancel} className={`${SECONDARY_BUTTON} mt-2`}>Hủy</button>
      <Alert text={error} />
    </form>
  );
}

interface CodeActionProps {
  label: string;
  submitLabel: string;
  hasPassword: boolean;
  send: (code: string, password?: string) => Promise<void>;
  onCancel: () => void;
}

/** Hỏi một mã hiện tại (mã ứng dụng hoặc mã khôi phục) trước khi tạo lại mã/tắt. */
function CodeAction({ label, submitLabel, hasPassword, send, onCancel }: CodeActionProps) {
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run, fail } = useAction();

  async function submit(event: FormEvent) {
    event.preventDefault();
    const clean = code.trim().toLowerCase();
    if (!clean) return fail("Hãy nhập mã");
    const ok = await run(() => send(clean, hasPassword ? password : undefined));
    setPassword("");
    if (!ok) setCode("");
  }

  return (
    <form onSubmit={submit} aria-label={submitLabel} className="mt-2">
      <label htmlFor="totp-action-code" className={LABEL}>{label}</label>
      <input id="totp-action-code" value={code} autoComplete="one-time-code" autoCapitalize="none" spellCheck={false}
             disabled={busy} onChange={(e) => setCode(e.target.value)} className={INPUT} />
      {hasPassword && <PasswordInput id="totp-action-password" value={password} onChange={setPassword} />}
      <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>{busy ? "Đang xử lý..." : submitLabel}</button>
      <button type="button" disabled={busy} onClick={onCancel} className={`${SECONDARY_BUTTON} mt-2`}>Hủy</button>
      <Alert text={error} />
    </form>
  );
}

interface EnabledProps {
  left: number;
  hasPassword: boolean;
  onCodes: (codes: string[]) => void;
  onDone: Done;
}

function EnabledView({ left, hasPassword, onCodes, onDone }: EnabledProps) {
  const [action, setAction] = useState<"regenerate" | "disable" | null>(null);
  const low = left <= LOW_CODES_THRESHOLD;

  async function regenerate(code: string, password?: string) {
    const { recovery_codes } = await totpRegenerateRecoveryCodes(code, password);
    setAction(null);
    onCodes(recovery_codes);
    await onDone();
  }

  async function disable(code: string, password?: string) {
    await totpDisable(code, password);
    await onDone();
  }

  return (
    <>
      <p className="text-sm font-medium mb-1">Trạng thái: đang BẬT</p>
      <p role={low ? "alert" : undefined}
         className={low ? "text-sm font-semibold text-amber-900 bg-amber-50 border border-amber-300 rounded p-2 mb-2" : "text-sm mb-2"}>
        Còn {left} mã khôi phục{low ? ". Hãy tạo lại mã mới sớm." : ""}
      </p>
      {action === null && (
        <div className="flex flex-col gap-2">
          <button type="button" className={SECONDARY_BUTTON} onClick={() => setAction("regenerate")}>Tạo lại mã khôi phục</button>
          <button type="button" className={SECONDARY_BUTTON} onClick={() => setAction("disable")}>Tắt</button>
        </div>
      )}
      {action === "regenerate" && (
        <CodeAction label="Mã xác thực hiện tại (mã cũ sẽ không dùng được nữa)" submitLabel="Xác nhận tạo lại mã"
                    hasPassword={hasPassword} send={regenerate} onCancel={() => setAction(null)} />
      )}
      {action === "disable" && (
        <CodeAction label="Mã xác thực hoặc mã khôi phục" submitLabel="Xác nhận tắt"
                    hasPassword={hasPassword} send={disable} onCancel={() => setAction(null)} />
      )}
    </>
  );
}

/** Thẻ Xác thực hai bước: bật (QR + mã), hiển thị mã khôi phục một lần, tạo lại mã, tắt. */
export default function TotpMethod({ enabled, recoveryCodesLeft, hasPassword, onDone }: Props) {
  const [setup, setSetup] = useState<{ data: TotpSetup; password?: string } | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);

  let body;
  if (codes) {
    body = <RecoveryCodesBox codes={codes} onDismiss={() => setCodes(null)} />;
  } else if (enabled) {
    body = <EnabledView left={recoveryCodesLeft} hasPassword={hasPassword} onCodes={setCodes} onDone={onDone} />;
  } else if (setup) {
    body = (
      <ConfirmSetup
        setup={setup.data}
        password={setup.password}
        onCancel={() => setSetup(null)}
        onEnabled={async (recovery) => {
          setSetup(null);
          setCodes(recovery);
          await onDone();
        }}
      />
    );
  } else {
    body = <StartSetup hasPassword={hasPassword} onStarted={(data, password) => setSetup({ data, password })} />;
  }

  return (
    <section aria-label={TOTP_TITLE} className={SECTION}>
      <h2 className="font-bold mb-1">{TOTP_TITLE}</h2>
      {!enabled && !codes && <p className="text-sm font-medium mb-1">Trạng thái: đang TẮT (mặc định)</p>}
      <p className={NOTE}>{TOTP_HINT}</p>
      {body}
    </section>
  );
}
