"use client";

import { FormEvent, useState } from "react";

import Alert from "@sn/elements/Alert";
import { CARD, INPUT, LABEL, LINK_BUTTON, NOTE, PRIMARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { EMAIL_INVALID, NEUTRAL_RESET_MESSAGE, forgotPassword, isEmailValid } from "../lib/auth";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import Link from "next/link";
import TextBox from "@sn/elements/TextBox";

/** Quên mật khẩu: luôn hiện cùng một xác nhận, không tiết lộ email có tài khoản hay không. */
export default function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const { busy, error, run, fail } = useAction();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!isEmailValid(email)) return fail(EMAIL_INVALID);
    if (await run(async () => void (await forgotPassword(email)))) setSent(true);
  }

  return (
    <main className={CARD}>
      <h1 className="text-2xl font-bold mb-4">{tr("quen_mat_khau_2")}</h1>
      {sent ? (
        <p role="status" className="text-sm text-line mb-2">{NEUTRAL_RESET_MESSAGE}</p>
      ) : (
        <form onSubmit={submit} aria-label={tr("quen_mat_khau_2")}>
          <label htmlFor="forgot-email" className={LABEL}>Email</label>
          <TextBox id="forgot-email" type="email" name="email" value={email} required autoComplete="email" inputMode="email"
                 onChange={(e) => setEmail(e.target.value)} className={INPUT} />
          <p className={NOTE}>{tr("nhap_email_cua_tai_khoan_chung")}</p>
          <Button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
            {busy ? tr("dang_gui") : tr("gui_lien_ket_dat_lai")}
          </Button>
          <div className="text-center"><Alert className="mt-2">{error}</Alert></div>
        </form>
      )}
      <Link href="/user" className={`${LINK_BUTTON} block text-center`}>{tr("quay_lai_dang_nhap")}</Link>
    </main>
  );
}
