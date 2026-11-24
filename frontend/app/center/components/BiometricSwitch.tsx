"use client";

import { FormEvent, ReactNode, useState } from "react";

import Alert from "@sn/elements/Alert";
import { INPUT, LABEL, NOTE, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";
import Button from "@sn/elements/Button";
import { usePasswordProof } from "./PasswordConfirm";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

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
  const { password, setPassword, isShared } = usePasswordProof();
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
        {tr("trang_thai")} {enabled ? tr("dang_bat") : tr("dang_tat_mac_dinh")}
      </p>
      <p className={NOTE}>{description}</p>
      {warning}
      {blocked && <p className="text-sm text-line mb-2">{requirement}</p>}
      {hasPassword && !blocked && !isShared && (
        <>
          <label htmlFor={`${id}-password`} className={LABEL}>{tr("nhap_lai_mat_khau_de_xac")}</label>
          <TextBox id={`${id}-password`} type="password" value={password} autoComplete="current-password" required
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </>
      )}
      <Button type="submit" disabled={busy || blocked}
              className={`w-full p-2 rounded font-bold text-line disabled:opacity-50 ${enabled ? "bg-solid-2" : "bg-solid-1"}`}>
        {busy ? tr("dang_luu") : enabled ? props.disableLabel : props.enableLabel}
      </Button>
      <Alert className="mt-2">{error}</Alert>
      {dialog}
    </form>
  );
}
