"use client";

import { FormEvent, useState } from "react";

import { useAccountChange } from "./AccountChanges";
import Alert from "@sn/elements/Alert";
import ApplyButton from "./ApplyButton";
import { INPUT, LABEL, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";
import { EMAIL_INVALID, Me, isEmailValid, removeMyEmail, setMyEmail, verifyEmailCode } from "../lib/auth";
import Button from "@sn/elements/Button";
import { usePasswordProof } from "./PasswordConfirm";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

interface Props {
  me: Me;
  onDone: () => void | Promise<void>;
}

const EMAIL_NOTE = tr("email_da_xac_minh_dung_de");

/** Thêm/đổi email, nhập mã xác minh, gửi lại mã và xóa email. `Me` là nguồn sự thật, tải lại sau mỗi thay đổi. */
export default function EmailMethod({ me, onDone }: Props) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const { password, setPassword, isShared } = usePasswordProof();
  const { busy, error, message, run, fail } = useAction();
  const { withReauth, dialog } = useReauth();
  const needsPassword = me.has_password;
  const unverified = Boolean(me.email) && !me.email_verified;

  /** Same code for the form's own button and for the page's "Đổi tài khoản": true when the code was sent. */
  async function apply(): Promise<boolean> {
    if (!isEmailValid(email)) {
      fail(EMAIL_INVALID);
      return false;
    }
    const target = email.trim();
    const ok = await run(async () => {
      await withReauth(() => setMyEmail(target, needsPassword ? password : undefined));
      return tr("chung_toi_da_gui_ma_xac", { target });
    });
    if (!ok) return false;
    setEmail("");
    setPassword("");
    await onDone();
    return true;
  }

  useAccountChange("cach-email", "Email", email.trim() !== "", apply);

  function saveEmail(event: FormEvent) {
    event.preventDefault();
    void apply();
  }

  async function verify(event: FormEvent) {
    event.preventDefault();
    if (!/^\d{6}$/.test(code.trim())) return fail(tr("ma_gom_6_chu_so"));
    const ok = await run(async () => {
      await verifyEmailCode(code);
      return tr("da_xac_minh_email");
    });
    if (!ok) return;
    setCode("");
    await onDone();
  }

  async function resend() {
    if (!me.email) return;
    const target = me.email;
    const ok = await run(async () => {
      await withReauth(() => setMyEmail(target, needsPassword ? password : undefined));
      return tr("da_gui_lai_ma_xac_minh", { target });
    });
    if (ok) setPassword("");
  }

  async function remove() {
    const ok = await run(async () => {
      await withReauth(() => removeMyEmail(needsPassword ? password : undefined));
      return tr("da_xoa_email");
    });
    if (!ok) return;
    setPassword("");
    await onDone();
  }

  return (
    <div className="mt-1">
      <p className="text-xs text-line mb-2">{EMAIL_NOTE}</p>
      {unverified && (
        <form onSubmit={verify} aria-label={tr("xac_minh_email")}>
          <label htmlFor="email-code" className={LABEL}>{tr("ma_xac_minh_6_chu_so")}</label>
          <TextBox id="email-code" value={code} inputMode="numeric" autoComplete="one-time-code" maxLength={6} required
                 onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className={INPUT} />
          <Button type="submit" disabled={busy} className={PRIMARY_BUTTON}>{tr("xac_minh")}</Button>
          <Button variant="secondary" type="button" disabled={busy} onClick={() => void resend()} className={`${SECONDARY_BUTTON} mt-2`}>
            {tr("gui_lai")}
          </Button>
        </form>
      )}
      <form onSubmit={saveEmail} aria-label={me.email ? tr("doi_email") : tr("them_email")}>
        <label htmlFor="email-new" className={LABEL}>{me.email ? tr("email_moi") : tr("dia_chi_email")}</label>
        <TextBox id="email-new" type="email" value={email} autoComplete="email" inputMode="email" required
               onChange={(e) => setEmail(e.target.value)} className={INPUT} />
        <ApplyButton variant="secondary" disabled={busy} className={SECONDARY_BUTTON}>
          {me.email ? tr("doi_email") : tr("them_email")}
        </ApplyButton>
      </form>
      {needsPassword && !isShared && (
        <div className="mt-2">
          <label htmlFor="email-password" className={LABEL}>{tr("nhap_lai_mat_khau_de_xac")}</label>
          <TextBox id="email-password" type="password" value={password} autoComplete="current-password"
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </div>
      )}
      {me.email && (
        <Button variant="secondary" type="button" disabled={busy} onClick={() => void remove()} className={`${SECONDARY_BUTTON} mt-2`}>
          {tr("xoa_email")}
        </Button>
      )}
      <Alert className="mt-2">{error}</Alert>
      <Alert tone="success" className="mt-2">{message}</Alert>
      {dialog}
    </div>
  );
}
