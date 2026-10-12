"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import Alert from "./Alert";
import GoogleSignInButton from "./GoogleSignInButton";
import { digitsOnly, TOTP_LENGTH } from "./TotpLoginForm";
import { INPUT, LABEL, NOTE, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { usePasskeySupport } from "../hooks/usePasskeySupport";
import { NO_CONFIG, getAuthConfig, reauthEmailRequest, reauthEmailVerify, reauthGoogle, reauthPasskey } from "../lib/auth";
import { PASSKEY_UNSUPPORTED } from "../lib/passkey";

interface Props {
  /** Methods the server accepts (subset of passkey/google/email); unknown ones are ignored. */
  methods: string[];
  onSuccess: () => void;
  onCancel: () => void;
}

export const REAUTH_TITLE = "Xác minh lại danh tính";
export const REAUTH_CANCELLED = "Bạn đã hủy bước xác minh lại.";
const NO_METHOD = "Không có cách xác minh phù hợp. Hãy đăng xuất rồi đăng nhập lại.";
const NO_GOOGLE = "Đăng nhập Google chưa được cấu hình.";

function GoogleOption({ onToken, onError }: { onToken: (token: string) => void; onError: (text: string) => void }) {
  const [clientId, setClientId] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    getAuthConfig().then((config) => setClientId(config.google_client_id)).catch(() => setClientId(NO_CONFIG.google_client_id));
  }, []);
  if (clientId === undefined) return <p role="status" className={NOTE}>Đang tải...</p>;
  if (!clientId) return <p role="note" className="text-sm text-red-600 mb-2">{NO_GOOGLE}</p>;
  return (
    <div className="mb-2">
      <p className={NOTE}>Đăng nhập lại bằng Google</p>
      <GoogleSignInButton clientId={clientId} onCredential={onToken} onError={onError} />
    </div>
  );
}

/** Modal asking the user to prove their identity again (only with the methods the server offered). */
export default function ReauthDialog({ methods, onSuccess, onCancel }: Props) {
  const supported = usePasskeySupport();
  const [codeSent, setCodeSent] = useState(false);
  const [code, setCode] = useState("");
  const { busy, error, run, fail } = useAction();
  const root = useRef<HTMLDivElement>(null);
  const hasPasskey = methods.includes("passkey");
  const hasGoogle = methods.includes("google");
  const hasEmail = methods.includes("email");

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    root.current?.focus();
    // Deferred: the opener is still disabled (busy) until the cancelled/finished action settles.
    return () => void setTimeout(() => previous?.focus?.(), 0);
  }, []);

  async function attempt(action: () => Promise<unknown>): Promise<boolean> {
    const ok = await run(async () => void (await action()));
    if (ok) onSuccess();
    return ok;
  }

  async function sendCode() {
    if (await run(async () => void (await reauthEmailRequest()))) setCodeSent(true);
  }

  function verify(event: FormEvent) {
    event.preventDefault();
    if (code.length !== TOTP_LENGTH) return fail("Mã gồm 6 chữ số");
    void attempt(() => reauthEmailVerify(code));
  }

  function keyDown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onCancel();
    }
  }

  // Portal + stopPropagation: the dialog is opened from inside other forms, whose submit it must not trigger.
  return createPortal(
    <div onSubmit={(event) => event.stopPropagation()} className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        ref={root}
        role="dialog"
        aria-modal="true"
        aria-labelledby="reauth-title"
        tabIndex={-1}
        onKeyDown={keyDown}
        className="w-full max-w-sm rounded bg-white p-6 text-left text-gray-900 shadow"
      >
        <h2 id="reauth-title" className="font-bold mb-1">{REAUTH_TITLE}</h2>
        <p className={NOTE}>Thao tác này cần xác minh lại để bảo vệ tài khoản của bạn.</p>
        {!hasPasskey && !hasGoogle && !hasEmail && <p role="note" className="text-sm text-red-600 mb-2">{NO_METHOD}</p>}
        {hasPasskey && (
          <div className="mb-2">
            {!supported && <p role="note" className="text-sm text-red-600 mb-1">{PASSKEY_UNSUPPORTED}</p>}
            <button type="button" disabled={busy || !supported} className={PRIMARY_BUTTON}
                    onClick={() => void attempt(reauthPasskey)}>
              Dùng Passkey
            </button>
          </div>
        )}
        {hasGoogle && <GoogleOption onToken={(token) => void attempt(() => reauthGoogle(token))} onError={fail} />}
        {hasEmail && !codeSent && (
          <button type="button" disabled={busy} className={`${SECONDARY_BUTTON} mb-2`} onClick={() => void sendCode()}>
            Gửi mã qua email
          </button>
        )}
        {hasEmail && codeSent && (
          <form onSubmit={verify} aria-label="Nhập mã xác minh lại" className="mb-2">
            <p className={NOTE}>Chúng tôi đã gửi mã 6 chữ số tới email của bạn.</p>
            <label htmlFor="reauth-code" className={LABEL}>Mã xác minh (6 chữ số)</label>
            <input id="reauth-code" value={code} inputMode="numeric" autoComplete="one-time-code" maxLength={TOTP_LENGTH}
                   disabled={busy} onChange={(e) => setCode(digitsOnly(e.target.value))} className={INPUT} />
            <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>{busy ? "Đang xử lý..." : "Xác nhận"}</button>
            <button type="button" disabled={busy} className={`${SECONDARY_BUTTON} mt-2`} onClick={() => void sendCode()}>
              Gửi lại mã
            </button>
          </form>
        )}
        <Alert text={error} />
        <button type="button" disabled={busy} onClick={onCancel} className={`${SECONDARY_BUTTON} mt-2`}>Hủy</button>
      </div>
    </div>,
    document.body,
  );
}
