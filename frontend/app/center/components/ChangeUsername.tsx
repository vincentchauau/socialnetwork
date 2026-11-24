"use client";

import { FormEvent, ReactNode, useState } from "react";

import { setCsrfToken } from "@sn/api";
import { useAccountChange } from "./AccountChanges";
import Alert from "@sn/elements/Alert";
import ApplyButton from "./ApplyButton";
import UsernameField from "./UsernameField";
import { INPUT, LABEL, NOTE, PRIMARY_BUTTON, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";
import { changeUsername, usernameProblem } from "../lib/auth";
import Button from "@sn/elements/Button";
import { usePasswordProof } from "./PasswordConfirm";
import { tr } from "../i18n";
import { intlLocale } from "@sn/lib/i18n";
import TextBox from "@sn/elements/TextBox";

const USERNAME_NOTE =
  tr("moi_30_ngay_chi_doi_duoc");

interface Props {
  username: string;
  hasPassword: boolean;
  canRenameAfter: string | null;
  onDone: () => void | Promise<void>;
  /** Shown at the end of the card, outside the form (the account page puts its password confirmation there). */
  footer?: ReactNode;
}

/** The date from which renaming is allowed again, or null when it is allowed now (or the date is unusable). */
function futureDate(iso: string | null): Date | null {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) || date.getTime() <= Date.now() ? null : date;
}

export default function ChangeUsername({ username, hasPassword, canRenameAfter, onDone, footer }: Props) {
  const [next, setNext] = useState("");
  const { password, setPassword, isShared } = usePasswordProof();
  const { busy, error, message, run, fail } = useAction();
  const { withReauth, dialog } = useReauth();
  const waitUntil = futureDate(canRenameAfter);

  /** Same code for the form's own button and for the page's "Đổi tài khoản": true when the name was changed. */
  async function apply(): Promise<boolean> {
    const name = next.trim();
    const problem = usernameProblem(name);
    if (problem) {
      fail(problem);
      return false;
    }
    const ok = await run(() =>
      withReauth(async () => {
        const session = await changeUsername(name, hasPassword ? password : undefined);
        setCsrfToken(session.csrf_token);
        return tr("da_doi_ten_dang_nhap");
      }),
    );
    setPassword("");
    if (!ok) return false;
    setNext("");
    await onDone();
    return true;
  }

  useAccountChange("cach-username", tr("ten_dang_nhap"), next.trim() !== "", apply);

  function submit(event: FormEvent) {
    event.preventDefault();
    void apply();
  }

  return (
    <section className={SECTION}>
    <form onSubmit={submit} aria-label={tr("doi_ten_dang_nhap")}>
      <h2 className="font-bold mb-1">{tr("ten_dang_nhap")}</h2>
      <p className="mb-1">{tr("hien_tai")} <strong>{username}</strong></p>
      <p className={NOTE}>{USERNAME_NOTE}</p>
      {waitUntil && <p role="note" className="text-sm font-medium mb-2">{tr("co_the_doi_lai_tu")} {waitUntil.toLocaleDateString(intlLocale())}</p>}
      <fieldset disabled={busy || waitUntil !== null} className="border-0 p-0 m-0">
        <UsernameField value={next} onChange={setNext} />
        {hasPassword && !isShared && (
          <>
            <label htmlFor="rename-password" className={LABEL}>{tr("mat_khau_hien_tai_de_doi")}</label>
            <TextBox id="rename-password" type="password" value={password} autoComplete="current-password" required
                   onChange={(e) => setPassword(e.target.value)} className={INPUT} />
          </>
        )}
        <ApplyButton className={PRIMARY_BUTTON}>{busy ? tr("dang_luu") : tr("doi_ten")}</ApplyButton>
      </fieldset>
      <Alert className="mt-2">{error}</Alert>
      <Alert tone="success" className="mt-2">{message}</Alert>
      {dialog}
    </form>
    {footer}
    </section>
  );
}
