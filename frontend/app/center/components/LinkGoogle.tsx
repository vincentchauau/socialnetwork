"use client";

import { useState } from "react";

import Alert from "@sn/elements/Alert";
import GoogleSignInButton from "./GoogleSignInButton";
import { INPUT, LABEL, NOTE, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";
import { linkGoogle } from "../lib/auth";
import { usePasswordProof } from "./PasswordConfirm";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

interface Props {
  clientId: string;
  hasPassword: boolean;
  onDone: () => void | Promise<void>;
}

export default function LinkGoogle({ clientId, hasPassword, onDone }: Props) {
  const { password, setPassword, isShared } = usePasswordProof();
  const { busy, error, message, run, fail } = useAction();
  const { withReauth, dialog } = useReauth();

  async function link(idToken: string) {
    const ok = await run(async () => {
      await withReauth(() => linkGoogle(idToken, hasPassword ? password : undefined));
      return tr("da_lien_ket_tai_khoan_google");
    });
    if (ok) {
      setPassword("");
      await onDone();
    }
  }

  return (
    <section aria-label={tr("lien_ket_tai_khoan_google")} className={SECTION}>
      <h2 className="font-bold mb-1">{tr("lien_ket_tai_khoan_google")}</h2>
      <p className={NOTE}>{tr("lien_ket_de_lan_sau_dang")}</p>
      {hasPassword && !isShared && (
        <>
          <label htmlFor="link-google-password" className={LABEL}>{tr("nhap_lai_mat_khau_de_xac")}</label>
          <TextBox id="link-google-password" type="password" value={password} autoComplete="current-password"
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </>
      )}
      <div className="mb-2" aria-busy={busy}>
        <GoogleSignInButton clientId={clientId} onCredential={(token) => void link(token)} onError={fail} />
      </div>
      <Alert className="mt-2">{error}</Alert>
      <Alert tone="success" className="mt-2">{message}</Alert>
      {dialog}
    </section>
  );
}
