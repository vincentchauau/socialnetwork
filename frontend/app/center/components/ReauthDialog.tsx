"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import Alert from "@sn/elements/Alert";
import GoogleSignInButton from "./GoogleSignInButton";
import { digitsOnly, TOTP_LENGTH } from "./TotpLoginForm";
import { INPUT, LABEL, NOTE, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { usePasskeySupport } from "../hooks/usePasskeySupport";
import { NO_CONFIG, getAuthConfig, reauthEmailRequest, reauthEmailVerify, reauthGoogle, reauthPasskey } from "../lib/auth";
import { PASSKEY_UNSUPPORTED } from "../lib/passkey";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

interface Props {
  /** Methods the server accepts (subset of passkey/google/email); unknown ones are ignored. */
  methods: string[];
  onSuccess: () => void;
  onCancel: () => void;
}

const REAUTH_TITLE = tr("xac_minh_lai_danh_tinh");
export const REAUTH_CANCELLED = tr("ban_da_huy_buoc_xac_minh");
const NO_METHOD = tr("khong_co_cach_xac_minh_phu");
const NO_GOOGLE = tr("dang_nhap_google_chua_duoc_cau");

function GoogleOption({ onToken, onError }: { onToken: (token: string) => void; onError: (text: string) => void }) {
  const [clientId, setClientId] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    getAuthConfig().then((config) => setClientId(config.google_client_id)).catch(() => setClientId(NO_CONFIG.google_client_id));
  }, []);
  if (clientId === undefined) return <p role="status" className={NOTE}>{tr("dang_tai")}</p>;
  if (!clientId) return <p role="note" className="text-sm text-line mb-2">{NO_GOOGLE}</p>;
  return (
    <div className="mb-2">
      <p className={NOTE}>{tr("dang_nhap_lai_bang_google")}</p>
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
    if (code.length !== TOTP_LENGTH) return fail(tr("ma_gom_6_chu_so"));
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
        className="w-full max-w-sm rounded bg-solid p-6 text-left text-line shadow"
      >
        <h2 id="reauth-title" className="font-bold mb-1">{REAUTH_TITLE}</h2>
        <p className={NOTE}>{tr("thao_tac_nay_can_xac_minh")}</p>
        {!hasPasskey && !hasGoogle && !hasEmail && <p role="note" className="text-sm text-line mb-2">{NO_METHOD}</p>}
        {hasPasskey && (
          <div className="mb-2">
            {!supported && <p role="note" className="text-sm text-line mb-1">{PASSKEY_UNSUPPORTED}</p>}
            <Button type="button" disabled={busy || !supported} className={PRIMARY_BUTTON}
                    onClick={() => void attempt(reauthPasskey)}>
              {tr("dung_passkey")}
            </Button>
          </div>
        )}
        {hasGoogle && <GoogleOption onToken={(token) => void attempt(() => reauthGoogle(token))} onError={fail} />}
        {hasEmail && !codeSent && (
          <Button variant="secondary" type="button" disabled={busy} className={`${SECONDARY_BUTTON} mb-2`} onClick={() => void sendCode()}>
            {tr("gui_ma_qua_email")}
          </Button>
        )}
        {hasEmail && codeSent && (
          <form onSubmit={verify} aria-label={tr("nhap_ma_xac_minh_lai")} className="mb-2">
            <p className={NOTE}>{tr("chung_toi_da_gui_ma_6")}</p>
            <label htmlFor="reauth-code" className={LABEL}>{tr("ma_xac_minh_6_chu_so")}</label>
            <TextBox id="reauth-code" value={code} inputMode="numeric" autoComplete="one-time-code" maxLength={TOTP_LENGTH}
                   disabled={busy} onChange={(e) => setCode(digitsOnly(e.target.value))} className={INPUT} />
            <Button type="submit" disabled={busy} className={PRIMARY_BUTTON}>{busy ? tr("dang_xu_ly") : tr("xac_nhan")}</Button>
            <Button variant="secondary" type="button" disabled={busy} className={`${SECONDARY_BUTTON} mt-2`} onClick={() => void sendCode()}>
              {tr("gui_lai_ma")}
            </Button>
          </form>
        )}
        <Alert className="mt-2">{error}</Alert>
        <Button variant="secondary" type="button" disabled={busy} onClick={onCancel} className={`${SECONDARY_BUTTON} mt-2`}>{tr("huy")}</Button>
      </div>
    </div>,
    document.querySelector<HTMLElement>(".app-center") ?? document.body,  // (inside the wrapper, so the CSS scoped to it applies)
  );
}
