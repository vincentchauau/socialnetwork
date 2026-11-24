"use client";

import { ApiError } from "@sn/api";
import { FormEvent, useEffect, useRef, useState } from "react";

import Alert from "@sn/elements/Alert";
import { INPUT, LABEL, LINK_BUTTON, PRIMARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { errorText, loginWithTotp } from "../lib/auth";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

export const TOTP_LENGTH = 6;
const WRONG_CODE = tr("ma_khong_dung_hoac_da_dung");
const TOO_MANY_CODES = tr("thu_qua_nhieu_lan_hay_doi");

/** Authenticator codes keep digits only; recovery codes are trimmed and lowercased. */
export const digitsOnly = (value: string) => value.replace(/\D/g, "").slice(0, TOTP_LENGTH);
export const normaliseRecoveryCode = (value: string) => value.trim().toLowerCase();

export function codeError(caught: unknown): Error {
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
    <form onSubmit={submit} aria-label={recovery ? tr("nhap_ma_khoi_phuc") : tr("nhap_ma_xac_thuc")}>
      <label htmlFor="mfa-code" className={LABEL}>
        {recovery ? tr("ma_khoi_phuc") : tr("ma_xac_thuc_6_chu_so")}
      </label>
      {recovery ? (
        <TextBox id="mfa-code" ref={input} value={value} disabled={busy} autoComplete="off" autoCapitalize="none"
               spellCheck={false} onChange={(e) => setValue(e.target.value)} className={INPUT} />
      ) : (
        <TextBox id="mfa-code" ref={input} value={value} disabled={busy} inputMode="numeric" autoComplete="one-time-code"
               maxLength={TOTP_LENGTH} onChange={(e) => setValue(digitsOnly(e.target.value))} className={INPUT} />
      )}
      <Button type="submit" disabled={busy || !ready} className={PRIMARY_BUTTON}>
        {busy ? tr("dang_xu_ly") : tr("xac_minh_va_dang_nhap")}
      </Button>
      <Button variant="ghost" type="button" disabled={busy} onClick={toggle} className={LINK_BUTTON}>
        {recovery ? tr("dung_ma_tu_ung_dung_xac") : tr("dung_ma_khoi_phuc")}
      </Button>
      <Alert className="mt-2">{error}</Alert>
    </form>
  );
}
