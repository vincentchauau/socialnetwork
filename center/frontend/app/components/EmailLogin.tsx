"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
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

export const RESEND_SECONDS = 30;
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
    if (!CODE_PATTERN.test(code)) return request.fail("Mã gồm 6 chữ số");
    void signIn(() => verifyEmailLogin(email, code));
  }

  function changeEmail() {
    setSent(false);
    setCode("");
    request.fail("");
  }

  if (!sent) {
    return (
      <form onSubmit={submitEmail} aria-label="Đăng nhập bằng email">
        <label htmlFor="login-email" className={LABEL}>Email</label>
        <input id="login-email" type="email" name="email" value={email} required autoComplete="email" inputMode="email"
               onChange={(e) => setEmail(e.target.value)} className={INPUT} />
        <p className={NOTE}>Chúng tôi sẽ gửi mã 6 số và một liên kết đăng nhập tới email này.</p>
        <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
          {request.busy ? "Đang gửi..." : "Gửi mã đăng nhập"}
        </button>
        <div className="text-center"><Alert text={request.error} /></div>
      </form>
    );
  }

  return (
    <form onSubmit={submitCode} aria-label="Nhập mã đăng nhập">
      <Alert text={request.message ?? NEUTRAL_SIGN_IN_MESSAGE} ok />
      <p className={NOTE}>Email: {email}</p>
      <label htmlFor="login-code" className={LABEL}>Mã 6 chữ số</label>
      <input id="login-code" name="code" value={code} required inputMode="numeric" autoComplete="one-time-code"
             pattern="[0-9]{6}" maxLength={6} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className={INPUT} />
      <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
        {signInBusy ? "Đang xử lý..." : "Đăng nhập"}
      </button>
      <button type="button" disabled={busy || cooldown.left > 0} onClick={() => void send()} className={`${SECONDARY_BUTTON} mt-2`}>
        {cooldown.left > 0 ? `Gửi lại (${cooldown.left}s)` : "Gửi lại"}
      </button>
      <button type="button" disabled={busy} onClick={changeEmail} className={LINK_BUTTON}>Đổi email</button>
      <div className="text-center"><Alert text={request.error} /></div>
    </form>
  );
}
