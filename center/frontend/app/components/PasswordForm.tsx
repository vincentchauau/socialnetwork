"use client";

import { FormEvent, useState } from "react";

import { setCsrfToken } from "@sn/api";
import Alert from "./Alert";
import { INPUT, LABEL, NOTE, PRIMARY_BUTTON, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { PASSWORD_MESSAGE, changePassword, isPasswordValid } from "../lib/auth";

interface Props {
  hasPassword: boolean;
  onDone: () => void | Promise<void>;
}

export default function PasswordForm({ hasPassword, onDone }: Props) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const { busy, error, message, run, fail } = useAction();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!isPasswordValid(next)) return fail(PASSWORD_MESSAGE);
    if (next !== confirm) return fail("Mật khẩu nhập lại không khớp");
    const ok = await run(async () => {
      const session = await changePassword(next, hasPassword ? current : undefined);
      setCsrfToken(session.csrf_token);
      return "Đã cập nhật mật khẩu.";
    });
    if (ok) {
      setCurrent("");
      setNext("");
      setConfirm("");
      await onDone();
    }
  }

  return (
    <form onSubmit={submit} aria-label="Đổi mật khẩu" className={SECTION}>
      <h2 className="font-bold mb-1">{hasPassword ? "Đổi mật khẩu" : "Đặt mật khẩu"}</h2>
      {hasPassword && (
        <>
          <label htmlFor="current-password" className={LABEL}>Mật khẩu hiện tại</label>
          <input id="current-password" type="password" value={current} autoComplete="current-password" required
                 onChange={(e) => setCurrent(e.target.value)} className={INPUT} />
        </>
      )}
      <label htmlFor="new-password" className={LABEL}>Mật khẩu mới</label>
      <input id="new-password" type="password" value={next} autoComplete="new-password" required
             aria-describedby="new-password-hint" placeholder="Ít nhất 8 ký tự"
             onChange={(e) => setNext(e.target.value)} className={INPUT} />
      <p id="new-password-hint" className={NOTE}>{PASSWORD_MESSAGE}.</p>
      <label htmlFor="confirm-password" className={LABEL}>Nhập lại mật khẩu mới</label>
      <input id="confirm-password" type="password" value={confirm} autoComplete="new-password" required
             onChange={(e) => setConfirm(e.target.value)} className={INPUT} />
      <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
        {busy ? "Đang lưu..." : "Cập nhật mật khẩu"}
      </button>
      <Alert text={error} />
      <Alert text={message} ok />
    </form>
  );
}
