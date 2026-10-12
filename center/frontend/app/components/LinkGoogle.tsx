"use client";

import { useState } from "react";

import Alert from "./Alert";
import GoogleSignInButton from "./GoogleSignInButton";
import { INPUT, LABEL, NOTE, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { linkGoogle } from "../lib/auth";

interface Props {
  clientId: string;
  hasPassword: boolean;
  onDone: () => void | Promise<void>;
}

export default function LinkGoogle({ clientId, hasPassword, onDone }: Props) {
  const [password, setPassword] = useState("");
  const { busy, error, message, run, fail } = useAction();

  async function link(idToken: string) {
    const ok = await run(async () => {
      await linkGoogle(idToken, hasPassword ? password : undefined);
      return "Đã liên kết tài khoản Google.";
    });
    if (ok) {
      setPassword("");
      await onDone();
    }
  }

  return (
    <section aria-label="Liên kết tài khoản Google" className={SECTION}>
      <h2 className="font-bold mb-1">Liên kết tài khoản Google</h2>
      <p className={NOTE}>Liên kết để lần sau đăng nhập bằng Google.</p>
      {hasPassword && (
        <>
          <label htmlFor="link-google-password" className={LABEL}>Nhập lại mật khẩu để xác nhận</label>
          <input id="link-google-password" type="password" value={password} autoComplete="current-password"
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </>
      )}
      <div className="mb-2" aria-busy={busy}>
        <GoogleSignInButton clientId={clientId} onCredential={(token) => void link(token)} onError={fail} />
      </div>
      <Alert text={error} />
      <Alert text={message} ok />
    </section>
  );
}
