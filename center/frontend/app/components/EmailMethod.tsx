"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
import { INPUT, LABEL, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";
import { EMAIL_INVALID, Me, isEmailValid, removeMyEmail, setMyEmail, verifyEmailCode } from "../lib/auth";

interface Props {
  me: Me;
  onDone: () => void | Promise<void>;
}

export const EMAIL_NOTE = "Email đã xác minh dùng để đăng nhập, khôi phục tài khoản và nhận thông báo bảo mật.";

/** Thêm/đổi email, nhập mã xác minh, gửi lại mã và xóa email. `Me` là nguồn sự thật, tải lại sau mỗi thay đổi. */
export default function EmailMethod({ me, onDone }: Props) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, message, run, fail } = useAction();
  const { withReauth, dialog } = useReauth();
  const needsPassword = me.has_password;
  const unverified = Boolean(me.email) && !me.email_verified;

  async function saveEmail(event: FormEvent) {
    event.preventDefault();
    if (!isEmailValid(email)) return fail(EMAIL_INVALID);
    const target = email.trim();
    const ok = await run(async () => {
      await withReauth(() => setMyEmail(target, needsPassword ? password : undefined));
      return `Chúng tôi đã gửi mã xác minh tới ${target}.`;
    });
    if (!ok) return;
    setEmail("");
    setPassword("");
    await onDone();
  }

  async function verify(event: FormEvent) {
    event.preventDefault();
    if (!/^\d{6}$/.test(code.trim())) return fail("Mã gồm 6 chữ số");
    const ok = await run(async () => {
      await verifyEmailCode(code);
      return "Đã xác minh email.";
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
      return `Đã gửi lại mã xác minh tới ${target}.`;
    });
    if (ok) setPassword("");
  }

  async function remove() {
    const ok = await run(async () => {
      await withReauth(() => removeMyEmail(needsPassword ? password : undefined));
      return "Đã xóa email.";
    });
    if (!ok) return;
    setPassword("");
    await onDone();
  }

  return (
    <div className="mt-1">
      <p className="text-xs text-gray-600 mb-2">{EMAIL_NOTE}</p>
      {unverified && (
        <form onSubmit={verify} aria-label="Xác minh email">
          <label htmlFor="email-code" className={LABEL}>Mã xác minh (6 chữ số)</label>
          <input id="email-code" value={code} inputMode="numeric" autoComplete="one-time-code" maxLength={6} required
                 onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className={INPUT} />
          <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>Xác minh</button>
          <button type="button" disabled={busy} onClick={() => void resend()} className={`${SECONDARY_BUTTON} mt-2`}>
            Gửi lại
          </button>
        </form>
      )}
      <form onSubmit={saveEmail} aria-label={me.email ? "Đổi email" : "Thêm email"}>
        <label htmlFor="email-new" className={LABEL}>{me.email ? "Email mới" : "Địa chỉ email"}</label>
        <input id="email-new" type="email" value={email} autoComplete="email" inputMode="email" required
               onChange={(e) => setEmail(e.target.value)} className={INPUT} />
        <button type="submit" disabled={busy} className={SECONDARY_BUTTON}>
          {me.email ? "Đổi email" : "Thêm email"}
        </button>
      </form>
      {needsPassword && (
        <div className="mt-2">
          <label htmlFor="email-password" className={LABEL}>Nhập lại mật khẩu để xác nhận</label>
          <input id="email-password" type="password" value={password} autoComplete="current-password"
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </div>
      )}
      {me.email && (
        <button type="button" disabled={busy} onClick={() => void remove()} className={`${SECONDARY_BUTTON} mt-2`}>
          Xóa email
        </button>
      )}
      <Alert text={error} />
      <Alert text={message} ok />
      {dialog}
    </div>
  );
}
