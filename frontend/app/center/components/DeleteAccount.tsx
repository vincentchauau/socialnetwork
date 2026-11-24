"use client";

import { FormEvent, useState } from "react";

import Alert from "@sn/elements/Alert";
import { DANGER_BUTTON, INPUT, LABEL, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";
import { deleteAccount } from "../lib/auth";
import { goTo } from "../lib/navigate";
import Button from "@sn/elements/Button";
import { usePasswordProof } from "./PasswordConfirm";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

const DELETE_PHRASE = "XOA";

export default function DeleteAccount({ hasPassword }: { hasPassword: boolean }) {
  const [phrase, setPhrase] = useState("");
  const { password, setPassword, isShared } = usePasswordProof();
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
    <form onSubmit={submit} aria-label={tr("xoa_tai_khoan")} className={`${SECTION} border-line`}>
      <h2 className="font-bold mb-1 text-line">{tr("xoa_tai_khoan")}</h2>
      <p className="text-sm text-line mb-2">
        {tr("xoa_vinh_vien_tai_khoan_va")} {DELETE_PHRASE} {tr("de_xac_nhan")}
      </p>
      <label htmlFor="delete-phrase" className={LABEL}>{tr("xac_nhan")}</label>
      <TextBox id="delete-phrase" value={phrase} onChange={(e) => setPhrase(e.target.value)} autoComplete="off" className={INPUT} />
      {hasPassword && !isShared && (
        <>
          <label htmlFor="delete-password" className={LABEL}>{tr("nhap_lai_mat_khau_de_xac")}</label>
          <TextBox id="delete-password" type="password" value={password} autoComplete="current-password" required
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </>
      )}
      <Button variant="danger" type="submit" disabled={busy || !confirmed} className={DANGER_BUTTON}>
        {busy ? tr("dang_xoa") : tr("xoa_tai_khoan_cua_toi")}
      </Button>
      <Alert className="mt-2">{error}</Alert>
      {dialog}
    </form>
  );
}
