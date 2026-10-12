"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
import { INPUT, LABEL, SECONDARY_BUTTON, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { deleteBiometrics } from "../lib/auth";

interface Props {
  hasPassword: boolean;
  onDone: () => void | Promise<void>;
}

export default function RemoveBiometrics({ hasPassword, onDone }: Props) {
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent) {
    event.preventDefault();
    const ok = await run(async () => void (await deleteBiometrics(hasPassword ? password : undefined)));
    if (ok) {
      setPassword("");
      await onDone();
    }
  }

  return (
    <form onSubmit={submit} aria-label="Xóa giọng nói và khuôn mặt" className={SECTION}>
      <h2 className="font-bold mb-1">Xóa dữ liệu giọng nói và khuôn mặt</h2>
      <p className="text-sm text-gray-600 mb-3">
        Xóa sẽ tắt đăng nhập không mật khẩu; đăng nhập bằng mật khẩu hoặc Google không đổi.
      </p>
      {hasPassword && (
        <>
          <label htmlFor="remove-password" className={LABEL}>Nhập lại mật khẩu để xác nhận</label>
          <input id="remove-password" type="password" value={password} autoComplete="current-password" required
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </>
      )}
      <button type="submit" disabled={busy} className={SECONDARY_BUTTON}>
        {busy ? "Đang xóa..." : "Xóa dữ liệu giọng nói và khuôn mặt"}
      </button>
      <Alert text={error} />
    </form>
  );
}
