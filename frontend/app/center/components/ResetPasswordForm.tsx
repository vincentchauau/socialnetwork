"use client";

import { FormEvent, useState } from "react";

import { ApiError } from "@sn/api";
import Alert from "@sn/elements/Alert";
import PasswordField from "./PasswordField";
import { CARD, INPUT, LABEL, LINK_BUTTON, PRIMARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { useUrlToken } from "../hooks/useUrlToken";
import { PASSWORD_MESSAGE, isPasswordValid, resetPassword } from "../lib/auth";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import Link from "next/link";
import TextBox from "@sn/elements/TextBox";

/** Đặt lại mật khẩu bằng token trong liên kết email (token chỉ nằm trong bộ nhớ). */
export default function ResetPasswordForm() {
  const url = useUrlToken();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [expired, setExpired] = useState(false);
  const { busy, error, run, fail } = useAction();

  if (!url.ready) return <p role="status" className="text-center mt-10">{tr("dang_tai")}</p>;
  const token = url.token;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    if (!isPasswordValid(password)) return fail(PASSWORD_MESSAGE);
    if (password !== confirm) return fail(tr("mat_khau_nhap_lai_khong_khop"));
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
      <h1 className="text-2xl font-bold mb-4">{tr("dat_lai_mat_khau")}</h1>
      {done ? (
        <>
          <p role="status" className="text-sm text-line mb-2">{tr("da_doi_mat_khau_hay_dang")}</p>
          <Link href="/user" className={`${PRIMARY_BUTTON} block text-center`}>{tr("dang_nhap")}</Link>
        </>
      ) : !token || expired ? (
        <>
          <p role="alert" className="text-sm text-line mb-2">{tr("lien_ket_khong_hop_le_hoac")}</p>
          <Link href="/forgot-password" className={`${LINK_BUTTON} block text-center`}>{tr("yeu_cau_lien_ket_moi")}</Link>
        </>
      ) : (
        <form onSubmit={submit} aria-label={tr("dat_lai_mat_khau")}>
          <PasswordField value={password} onChange={setPassword} isRegister label={tr("mat_khau_moi")} />
          <label htmlFor="reset-confirm" className={LABEL}>{tr("nhap_lai_mat_khau_moi")}</label>
          <TextBox id="reset-confirm" type="password" value={confirm} autoComplete="new-password" required
                 onChange={(e) => setConfirm(e.target.value)} className={INPUT} />
          <Button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
            {busy ? tr("dang_luu") : tr("doi_mat_khau")}
          </Button>
          <div className="text-center"><Alert className="mt-2">{error}</Alert></div>
        </form>
      )}
    </main>
  );
}
