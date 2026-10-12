"use client";

import { ApiError } from "@sn/api";
import { FormEvent, useEffect, useRef, useState } from "react";

import Alert from "./Alert";
import { INPUT, LABEL, LINK_BUTTON, PRIMARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { errorText, loginWithTotp } from "../lib/auth";

export const TOTP_LENGTH = 6;
export const WRONG_CODE = "Mã không đúng hoặc đã dùng";
export const TOO_MANY_CODES = "Thử quá nhiều lần, hãy đợi rồi thử lại";

/** Authenticator codes keep digits only; recovery codes are trimmed and lowercased. */
export const digitsOnly = (value: string) => value.replace(/\D/g, "").slice(0, TOTP_LENGTH);
export const normaliseRecoveryCode = (value: string) => value.trim().toLowerCase();

function codeError(caught: unknown): Error {
  if (caught instanceof ApiError && caught.status === 401) return new Error(WRONG_CODE);
  if (caught instanceof ApiError && caught.status === 429) return new Error(TOO_MANY_CODES);
  return new Error(errorText(caught));
}

interface Props {
  mfaToken: string;
  onDone: () => void;
}

/** Bước hai bằng mã ứng dụng xác thực (6 số) hoặc mã khôi phục dùng một lần. */
export default function TotpLoginForm({ mfaToken, onDone }: Props) {
  const [recovery, setRecovery] = useState(false);
  const [value, setValue] = useState("");
  const { busy, error, run, fail } = useAction();
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => input.current?.focus(), [recovery]);

  function toggle() {
    setRecovery(!recovery);
    setValue("");
    fail("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const proof = recovery ? { recoveryCode: normaliseRecoveryCode(value) } : { code: value };
    const ok = await run(async () => {
      try {
        await loginWithTotp(mfaToken, proof);
      } catch (caught) {
        throw codeError(caught);
      }
    });
    if (ok) onDone();
    else setValue("");
  }

  const ready = recovery ? normaliseRecoveryCode(value) !== "" : value.length === TOTP_LENGTH;
  return (
    <form onSubmit={submit} aria-label={recovery ? "Nhập mã khôi phục" : "Nhập mã xác thực"}>
      <label htmlFor="mfa-code" className={LABEL}>
        {recovery ? "Mã khôi phục" : "Mã xác thực 6 chữ số"}
      </label>
      {recovery ? (
        <input id="mfa-code" ref={input} value={value} disabled={busy} autoComplete="off" autoCapitalize="none"
               spellCheck={false} onChange={(e) => setValue(e.target.value)} className={INPUT} />
      ) : (
        <input id="mfa-code" ref={input} value={value} disabled={busy} inputMode="numeric" autoComplete="one-time-code"
               maxLength={TOTP_LENGTH} onChange={(e) => setValue(digitsOnly(e.target.value))} className={INPUT} />
      )}
      <button type="submit" disabled={busy || !ready} className={PRIMARY_BUTTON}>
        {busy ? "Đang xử lý..." : "Xác minh và đăng nhập"}
      </button>
      <button type="button" disabled={busy} onClick={toggle} className={LINK_BUTTON}>
        {recovery ? "Dùng mã từ ứng dụng xác thực" : "Dùng mã khôi phục"}
      </button>
      <Alert text={error} />
    </form>
  );
}
