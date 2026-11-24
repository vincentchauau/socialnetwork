"use client";

import { FormEvent, useState } from "react";

import Alert from "@sn/elements/Alert";
import { INPUT, LABEL, LINK_BUTTON, NOTE, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { useCooldown } from "../hooks/useCooldown";
import {
  LoginResult,
  NEUTRAL_PHONE_MESSAGE,
  PHONE_INVALID,
  isPhoneValid,
  requestPhoneLogin,
  verifyPhoneLogin,
} from "../lib/auth";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

const PHONE_RESEND_SECONDS = 30;
const CODE_PATTERN = /^\d{6}$/;

interface Props {
  /** Runs a sign-in (busy lock, MFA hand-off, redirect) owned by the sign-in form. */
  signIn: (action: () => Promise<LoginResult | undefined>) => Promise<void>;
  busy: boolean;
}

/** Đăng nhập bằng SMS: bước 1 gửi mã, bước 2 nhập mã 6 số. Luôn hiện cùng một thông báo. */
export default function PhoneLogin({ signIn, busy: signInBusy }: Props) {
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const request = useAction();
  const cooldown = useCooldown();
  const busy = signInBusy || request.busy;

  async function send() {
    if (!isPhoneValid(phone)) return request.fail(PHONE_INVALID);
    const ok = await request.run(async () => {
      await requestPhoneLogin(phone);
      return NEUTRAL_PHONE_MESSAGE;
    });
    if (!ok) return;
    setSent(true);
    setCode("");
    cooldown.start(PHONE_RESEND_SECONDS);
  }

  function submitPhone(event: FormEvent) {
    event.preventDefault();
    void send();
  }

  function submitCode(event: FormEvent) {
    event.preventDefault();
    if (!CODE_PATTERN.test(code)) return request.fail(tr("ma_gom_6_chu_so"));
    void signIn(() => verifyPhoneLogin(phone, code));
  }

  function changePhone() {
    setSent(false);
    setCode("");
    request.fail("");
  }

  if (!sent) {
    return (
      <form onSubmit={submitPhone} aria-label={tr("dang_nhap_bang_dien_thoai")}>
        <label htmlFor="login-phone" className={LABEL}>{tr("so_dien_thoai")}</label>
        <TextBox id="login-phone" type="tel" name="phone" value={phone} required autoComplete="tel" inputMode="tel"
               placeholder="+84901234567" onChange={(e) => setPhone(e.target.value)} className={INPUT} />
        <p className={NOTE}>{tr("nhap_so_o_dang_quoc_te")}</p>
        <Button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
          {request.busy ? tr("dang_gui") : tr("gui_ma_sms")}
        </Button>
        <div className="text-center"><Alert className="mt-2">{request.error}</Alert></div>
      </form>
    );
  }

  return (
    <form onSubmit={submitCode} aria-label={tr("nhap_ma_sms")}>
      <Alert tone="success" className="mt-2">{request.message ?? NEUTRAL_PHONE_MESSAGE}</Alert>
      <p className={NOTE}>{tr("so_dien_thoai_2")} {phone}</p>
      <label htmlFor="login-phone-code" className={LABEL}>{tr("ma_6_chu_so")}</label>
      <TextBox id="login-phone-code" name="code" value={code} required inputMode="numeric" autoComplete="one-time-code"
             pattern="[0-9]{6}" maxLength={6} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className={INPUT} />
      <Button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
        {signInBusy ? tr("dang_xu_ly") : tr("dang_nhap")}
      </Button>
      <Button variant="secondary" type="button" disabled={busy || cooldown.left > 0} onClick={() => void send()} className={`${SECONDARY_BUTTON} mt-2`}>
        {cooldown.left > 0 ? tr("gui_lai_p0_s", { p0: cooldown.left }) : tr("gui_lai")}
      </Button>
      <Button variant="ghost" type="button" disabled={busy} onClick={changePhone} className={LINK_BUTTON}>{tr("doi_so_dien_thoai")}</Button>
      <div className="text-center"><Alert className="mt-2">{request.error}</Alert></div>
    </form>
  );
}
