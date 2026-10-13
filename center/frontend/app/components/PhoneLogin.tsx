"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
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

export const PHONE_RESEND_SECONDS = 30;
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
    if (!CODE_PATTERN.test(code)) return request.fail("Mã gồm 6 chữ số");
    void signIn(() => verifyPhoneLogin(phone, code));
  }

  function changePhone() {
    setSent(false);
    setCode("");
    request.fail("");
  }

  if (!sent) {
    return (
      <form onSubmit={submitPhone} aria-label="Đăng nhập bằng điện thoại">
        <label htmlFor="login-phone" className={LABEL}>Số điện thoại</label>
        <input id="login-phone" type="tel" name="phone" value={phone} required autoComplete="tel" inputMode="tel"
               placeholder="+84901234567" onChange={(e) => setPhone(e.target.value)} className={INPUT} />
        <p className={NOTE}>Nhập số ở dạng quốc tế, ví dụ +84901234567. Chúng tôi sẽ gửi mã 6 số qua SMS.</p>
        <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
          {request.busy ? "Đang gửi..." : "Gửi mã SMS"}
        </button>
        <div className="text-center"><Alert text={request.error} /></div>
      </form>
    );
  }

  return (
    <form onSubmit={submitCode} aria-label="Nhập mã SMS">
      <Alert text={request.message ?? NEUTRAL_PHONE_MESSAGE} ok />
      <p className={NOTE}>Số điện thoại: {phone}</p>
      <label htmlFor="login-phone-code" className={LABEL}>Mã 6 chữ số</label>
      <input id="login-phone-code" name="code" value={code} required inputMode="numeric" autoComplete="one-time-code"
             pattern="[0-9]{6}" maxLength={6} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className={INPUT} />
      <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
        {signInBusy ? "Đang xử lý..." : "Đăng nhập"}
      </button>
      <button type="button" disabled={busy || cooldown.left > 0} onClick={() => void send()} className={`${SECONDARY_BUTTON} mt-2`}>
        {cooldown.left > 0 ? `Gửi lại (${cooldown.left}s)` : "Gửi lại"}
      </button>
      <button type="button" disabled={busy} onClick={changePhone} className={LINK_BUTTON}>Đổi số điện thoại</button>
      <div className="text-center"><Alert text={request.error} /></div>
    </form>
  );
}
