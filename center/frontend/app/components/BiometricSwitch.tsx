"use client";

import { FormEvent, ReactNode, useState } from "react";

import Alert from "./Alert";
import { INPUT, LABEL, NOTE, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";

interface Props {
  id: string;
  title: string;
  enabled: boolean;
  hasPassword: boolean;
  /** Bật cần đủ điều kiện (đủ mẫu); tắt thì luôn được. */
  canEnable: boolean;
  requirement: string;
  description: string;
  warning?: ReactNode;
  enableLabel: string;
  disableLabel: string;
  save: (enabled: boolean, password?: string) => Promise<unknown>;
  onDone: () => void | Promise<void>;
}

/** Một công tắc sinh trắc học độc lập, mặc định TẮT, đổi trạng thái sau khi nhập lại mật khẩu. */
export default function BiometricSwitch(props: Props) {
  const { id, title, enabled, hasPassword, canEnable, requirement, description, warning } = props;
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();
  const { withReauth, dialog } = useReauth();
  const blocked = !enabled && !canEnable;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const ok = await run(() => withReauth(async () => void (await props.save(!enabled, hasPassword ? password : undefined))));
    if (ok) {
      setPassword("");
      await props.onDone();
    }
  }

  return (
    <form onSubmit={submit} aria-label={title} className={SECTION}>
      <h2 className="font-bold mb-1">{title}</h2>
      <p className="text-sm font-medium mb-1">
        Trạng thái: {enabled ? "đang BẬT" : "đang TẮT (mặc định)"}
      </p>
      <p className={NOTE}>{description}</p>
      {warning}
      {blocked && <p className="text-sm text-gray-700 mb-2">{requirement}</p>}
      {hasPassword && !blocked && (
        <>
          <label htmlFor={`${id}-password`} className={LABEL}>Nhập lại mật khẩu để xác nhận</label>
          <input id={`${id}-password`} type="password" value={password} autoComplete="current-password" required
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </>
      )}
      <button type="submit" disabled={busy || blocked}
              className={`w-full p-2 rounded font-bold text-white disabled:opacity-50 ${enabled ? "bg-gray-700" : "bg-blue-600"}`}>
        {busy ? "Đang lưu..." : enabled ? props.disableLabel : props.enableLabel}
      </button>
      <Alert text={error} />
      {dialog}
    </form>
  );
}
