"use client";

import { FormEvent, useState } from "react";

import { ApiError } from "@sn/api";
import Alert from "./Alert";
import PasswordField from "./PasswordField";
import { CARD, INPUT, LABEL, LINK_BUTTON, PRIMARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { useUrlToken } from "../hooks/useUrlToken";
import { PASSWORD_MESSAGE, isPasswordValid, resetPassword } from "../lib/auth";

/** Đặt lại mật khẩu bằng token trong liên kết email (token chỉ nằm trong bộ nhớ). */
export default function ResetPasswordForm() {
  const url = useUrlToken();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [expired, setExpired] = useState(false);
  const { busy, error, run, fail } = useAction();

  if (!url.ready) return <p role="status" className="text-center mt-10">Đang tải...</p>;
  const token = url.token;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    if (!isPasswordValid(password)) return fail(PASSWORD_MESSAGE);
    if (password !== confirm) return fail("Mật khẩu nhập lại không khớp");
    let invalid = false;
    const ok = await run(async () => {
      try {
        await resetPassword(token, password);
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 400) invalid = true;
        throw caught;
      }
    });
    setPassword("");
    setConfirm("");
    if (ok) setDone(true);
    else if (invalid) setExpired(true);
  }

  return (
    <main className={CARD}>
      <h1 className="text-2xl font-bold mb-4">Đặt lại mật khẩu</h1>
      {done ? (
        <>
          <p role="status" className="text-sm text-green-700 mb-2">Đã đổi mật khẩu. Hãy đăng nhập lại.</p>
          <a href="/login" className={`${PRIMARY_BUTTON} block text-center`}>Đăng nhập</a>
        </>
      ) : !token || expired ? (
        <>
          <p role="alert" className="text-sm text-red-600 mb-2">Liên kết không hợp lệ hoặc đã hết hạn.</p>
          <a href="/forgot-password" className={`${LINK_BUTTON} block text-center`}>Yêu cầu liên kết mới</a>
        </>
      ) : (
        <form onSubmit={submit} aria-label="Đặt lại mật khẩu">
          <PasswordField value={password} onChange={setPassword} isRegister label="Mật khẩu mới" />
          <label htmlFor="reset-confirm" className={LABEL}>Nhập lại mật khẩu mới</label>
          <input id="reset-confirm" type="password" value={confirm} autoComplete="new-password" required
                 onChange={(e) => setConfirm(e.target.value)} className={INPUT} />
          <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
            {busy ? "Đang lưu..." : "Đổi mật khẩu"}
          </button>
          <div className="text-center"><Alert text={error} /></div>
        </form>
      )}
    </main>
  );
}
