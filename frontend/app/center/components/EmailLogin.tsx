"use client";

import { FormEvent, useState } from "react";

import Alert from "@sn/elements/Alert";
import { INPUT, LABEL, LINK_BUTTON, NOTE, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { useCooldown } from "../hooks/useCooldown";
import {
  EMAIL_INVALID,
  LoginResult,
  NEUTRAL_SIGN_IN_MESSAGE,
  isEmailValid,
  requestEmailLogin,
  verifyEmailLogin,
} from "../lib/auth";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

const RESEND_SECONDS = 30;
const CODE_PATTERN = /^\d{6}$/;

interface Props {
  /** Runs a sign-in (busy lock, MFA hand-off, redirect) owned by the sign-in form. */
  signIn: (action: () => Promise<LoginResult | undefined>) => Promise<void>;
  busy: boolean;
}

/** Đăng nhập bằng email: bước 1 gửi mã + liên kết, bước 2 nhập mã 6 số. Luôn hiện cùng một thông báo. */
export default function EmailLogin({ signIn, busy: signInBusy }: Props) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const request = useAction();
  const cooldown = useCooldown();
  const busy = signInBusy || request.busy;

  async function send() {
    if (!isEmailValid(email)) return request.fail(EMAIL_INVALID);
    const ok = await request.run(async () => {
      await requestEmailLogin(email);
      return NEUTRAL_SIGN_IN_MESSAGE;
    });
    if (!ok) return;
    setSent(true);
    setCode("");
    cooldown.start(RESEND_SECONDS);
  }

  function submitEmail(event: FormEvent) {
    event.preventDefault();
    void send();
  }

  function submitCode(event: FormEvent) {
    event.preventDefault();
    if (!CODE_PATTERN.test(code)) return request.fail(tr("ma_gom_6_chu_so"));
    void signIn(() => verifyEmailLogin(email, code));
  }

  function changeEmail() {
    setSent(false);
    setCode("");
    request.fail("");
  }

  if (!sent) {
    return (
      <form onSubmit={submitEmail} aria-label={tr("dang_nhap_bang_email")}>
        <label htmlFor="login-email" className={LABEL}>Email</label>
        <TextBox id="login-email" type="email" name="email" value={email} required autoComplete="email" inputMode="email"
               onChange={(e) => setEmail(e.target.value)} className={INPUT} />
        <p className={NOTE}>{tr("chung_toi_se_gui_ma_6")}</p>
        <Button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
          {request.busy ? tr("dang_gui") : tr("gui_ma_dang_nhap")}
        </Button>
        <div className="text-center"><Alert className="mt-2">{request.error}</Alert></div>
      </form>
    );
  }

  return (
    <form onSubmit={submitCode} aria-label={tr("nhap_ma_dang_nhap")}>
      <Alert tone="success" className="mt-2">{request.message ?? NEUTRAL_SIGN_IN_MESSAGE}</Alert>
      <p className={NOTE}>Email: {email}</p>
      <label htmlFor="login-code" className={LABEL}>{tr("ma_6_chu_so")}</label>
      <TextBox id="login-code" name="code" value={code} required inputMode="numeric" autoComplete="one-time-code"
             pattern="[0-9]{6}" maxLength={6} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className={INPUT} />
      <Button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
        {signInBusy ? tr("dang_xu_ly") : tr("dang_nhap")}
      </Button>
      <Button variant="secondary" type="button" disabled={busy || cooldown.left > 0} onClick={() => void send()} className={`${SECONDARY_BUTTON} mt-2`}>
        {cooldown.left > 0 ? tr("gui_lai_p0_s", { p0: cooldown.left }) : tr("gui_lai")}
      </Button>
      <Button variant="ghost" type="button" disabled={busy} onClick={changeEmail} className={LINK_BUTTON}>{tr("doi_email")}</Button>
      <div className="text-center"><Alert className="mt-2">{request.error}</Alert></div>
    </form>
  );
}
