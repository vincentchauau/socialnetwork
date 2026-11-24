"use client";

import { FormEvent, useState } from "react";

import { setCsrfToken } from "@sn/api";
import { useAccountChange } from "./AccountChanges";
import Alert from "@sn/elements/Alert";
import ApplyButton from "./ApplyButton";
import { INPUT, LABEL, NOTE, PRIMARY_BUTTON, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import PasswordChecklist from "./PasswordChecklist";
import { PASSWORD_EXAMPLE, PASSWORD_MESSAGE, changePassword, isPasswordValid } from "../lib/auth";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

interface Props {
  hasPassword: boolean;
  onDone: () => void | Promise<void>;
}

export default function PasswordForm({ hasPassword, onDone }: Props) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const { busy, error, message, run, fail } = useAction();

  /** Same code for the form's own button and for the page's "Đổi tài khoản": true when the password was changed. */
  async function apply(): Promise<boolean> {
    const stop = (message: string) => {
      fail(message);
      return false;
    };
    if (hasPassword && !current) return stop(tr("hay_nhap_mat_khau_hien_tai"));
    if (!isPasswordValid(next)) return stop(PASSWORD_MESSAGE);
    if (next !== confirm) return stop(tr("mat_khau_nhap_lai_khong_khop"));
    const ok = await run(async () => {
      const session = await changePassword(next, hasPassword ? current : undefined);
      setCsrfToken(session.csrf_token);
      return tr("da_cap_nhat_mat_khau");
    });
    if (!ok) return false;
    setCurrent("");
    setNext("");
    setConfirm("");
    await onDone();
    return true;
  }

  useAccountChange("cach-password", tr("mat_khau"), Boolean(current || next || confirm), apply);

  function submit(event: FormEvent) {
    event.preventDefault();
    void apply();
  }

  return (
    <form onSubmit={submit} aria-label={tr("doi_mat_khau")} className={SECTION}>
      <h2 className="font-bold mb-1">{hasPassword ? tr("doi_mat_khau") : tr("dat_mat_khau")}</h2>
      {hasPassword && (
        <>
          <label htmlFor="current-password" className={LABEL}>{tr("mat_khau_hien_tai")}</label>
          <TextBox id="current-password" type="password" value={current} autoComplete="current-password" required
                 onChange={(e) => setCurrent(e.target.value)} className={INPUT} />
        </>
      )}
      <label htmlFor="new-password" className={LABEL}>{tr("mat_khau_moi")}</label>
      <TextBox id="new-password" type="password" value={next} autoComplete="new-password" required
             aria-describedby="new-password-hint" placeholder={`vd: ${PASSWORD_EXAMPLE}`}
             onChange={(e) => setNext(e.target.value)} className={INPUT} />
      <PasswordChecklist id="new-password-hint" password={next} />
      <label htmlFor="confirm-password" className={LABEL}>{tr("nhap_lai_mat_khau_moi")}</label>
      <TextBox id="confirm-password" type="password" value={confirm} autoComplete="new-password" required
             onChange={(e) => setConfirm(e.target.value)} className={INPUT} />
      <ApplyButton disabled={busy} className={PRIMARY_BUTTON}>
        {busy ? tr("dang_luu") : tr("cap_nhat_mat_khau")}
      </ApplyButton>
      <Alert className="mt-2">{error}</Alert>
      <Alert tone="success" className="mt-2">{message}</Alert>
    </form>
  );
}
