"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
import { DANGER_BUTTON, INPUT, LABEL, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";
import { deleteAccount } from "../lib/auth";
import { goTo } from "../lib/navigate";

export const DELETE_PHRASE = "XOA";

export default function DeleteAccount({ hasPassword }: { hasPassword: boolean }) {
  const [phrase, setPhrase] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();
  const { withReauth, dialog } = useReauth();
  const confirmed = phrase === DELETE_PHRASE;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!confirmed) return;
    const ok = await run(() => withReauth(() => deleteAccount(hasPassword ? password : undefined)));
    if (ok) goTo("/");
  }

  return (
    <form onSubmit={submit} aria-label="Xóa tài khoản" className={`${SECTION} border-red-600`}>
      <h2 className="font-bold mb-1 text-red-600">Xóa tài khoản</h2>
      <p className="text-sm text-gray-600 mb-2">
        Xóa vĩnh viễn tài khoản và mọi dữ liệu sinh trắc, không thể hoàn tác. Gõ {DELETE_PHRASE} để xác nhận.
      </p>
      <label htmlFor="delete-phrase" className={LABEL}>Xác nhận</label>
      <input id="delete-phrase" value={phrase} onChange={(e) => setPhrase(e.target.value)} autoComplete="off" className={INPUT} />
      {hasPassword && (
        <>
          <label htmlFor="delete-password" className={LABEL}>Nhập lại mật khẩu để xác nhận</label>
          <input id="delete-password" type="password" value={password} autoComplete="current-password" required
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </>
      )}
      <button type="submit" disabled={busy || !confirmed} className={DANGER_BUTTON}>
        {busy ? "Đang xóa..." : "Xóa tài khoản của tôi"}
      </button>
      <Alert text={error} />
      {dialog}
    </form>
  );
}
