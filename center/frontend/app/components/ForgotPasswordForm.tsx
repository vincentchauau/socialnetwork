"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
import { CARD, INPUT, LABEL, LINK_BUTTON, NOTE, PRIMARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { EMAIL_INVALID, NEUTRAL_RESET_MESSAGE, forgotPassword, isEmailValid } from "../lib/auth";

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
      <h1 className="text-2xl font-bold mb-4">Quên mật khẩu</h1>
      {sent ? (
        <p role="status" className="text-sm text-green-700 mb-2">{NEUTRAL_RESET_MESSAGE}</p>
      ) : (
        <form onSubmit={submit} aria-label="Quên mật khẩu">
          <label htmlFor="forgot-email" className={LABEL}>Email</label>
          <input id="forgot-email" type="email" name="email" value={email} required autoComplete="email" inputMode="email"
                 onChange={(e) => setEmail(e.target.value)} className={INPUT} />
          <p className={NOTE}>Nhập email của tài khoản, chúng tôi sẽ gửi liên kết đặt lại mật khẩu.</p>
          <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
            {busy ? "Đang gửi..." : "Gửi liên kết đặt lại"}
          </button>
          <div className="text-center"><Alert text={error} /></div>
        </form>
      )}
      <a href="/login" className={`${LINK_BUTTON} block text-center`}>Quay lại đăng nhập</a>
    </main>
  );
}
