"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
import { INPUT, LABEL, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";
import { Me, PHONE_INVALID, PHONE_SMS_WARNING, isPhoneValid, removeMyPhone, setMyPhone, verifyMyPhone } from "../lib/auth";

interface Props {
  me: Me;
  onDone: () => void | Promise<void>;
}

/** Thêm/đổi số điện thoại, nhập mã SMS xác minh và xóa số. `Me` là nguồn sự thật, tải lại sau mỗi thay đổi. */
export default function PhoneMethod({ me, onDone }: Props) {
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [awaitingCode, setAwaitingCode] = useState(false);
  const { busy, error, message, run, fail } = useAction();
  const { withReauth, dialog } = useReauth();
  const needsPassword = me.has_password;
  // The server stores a number only once it is verified, so `Me` never reports a pending one: remember it here.
  const unverified = awaitingCode || (Boolean(me.phone) && !me.phone_verified);

  async function savePhone(event: FormEvent) {
    event.preventDefault();
    if (!isPhoneValid(phone)) return fail(PHONE_INVALID);
    const ok = await run(async () => {
      await withReauth(() => setMyPhone(phone, needsPassword ? password : undefined));
      return "Chúng tôi đã gửi mã xác minh qua SMS.";
    });
    if (!ok) return;
    setPhone("");
    setPassword("");
    setAwaitingCode(true);
    await onDone();
  }

  async function verify(event: FormEvent) {
    event.preventDefault();
    if (!/^\d{6}$/.test(code.trim())) return fail("Mã gồm 6 chữ số");
    const ok = await run(async () => {
      await verifyMyPhone(code);
      return "Đã xác minh số điện thoại.";
    });
    if (!ok) return;
    setCode("");
    setAwaitingCode(false);
    await onDone();
  }

  async function remove() {
    const ok = await run(async () => {
      await withReauth(() => removeMyPhone(needsPassword ? password : undefined));
      return "Đã xóa số điện thoại.";
    });
    if (!ok) return;
    setPassword("");
    await onDone();
  }

  return (
    <div className="mt-1">
      <p role="note" className="text-xs text-amber-700 mb-2">{PHONE_SMS_WARNING}</p>
      {unverified && (
        <form onSubmit={verify} aria-label="Xác minh số điện thoại">
          <label htmlFor="phone-code" className={LABEL}>Mã SMS (6 chữ số)</label>
          <input id="phone-code" value={code} inputMode="numeric" autoComplete="one-time-code" maxLength={6} required
                 onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className={INPUT} />
          <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>Xác minh số</button>
        </form>
      )}
      <form onSubmit={savePhone} aria-label={me.phone ? "Đổi số điện thoại" : "Thêm số điện thoại"}>
        <label htmlFor="phone-new" className={LABEL}>{me.phone ? "Số điện thoại mới" : "Số điện thoại"}</label>
        <input id="phone-new" type="tel" value={phone} autoComplete="tel" inputMode="tel" placeholder="+84901234567" required
               onChange={(e) => setPhone(e.target.value)} className={INPUT} />
        <button type="submit" disabled={busy} className={SECONDARY_BUTTON}>
          {me.phone ? "Đổi số điện thoại" : "Thêm số điện thoại"}
        </button>
      </form>
      {needsPassword && (
        <div className="mt-2">
          <label htmlFor="phone-password" className={LABEL}>Nhập lại mật khẩu để xác nhận</label>
          <input id="phone-password" type="password" value={password} autoComplete="current-password"
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </div>
      )}
      {me.phone && (
        <button type="button" disabled={busy} onClick={() => void remove()} className={`${SECONDARY_BUTTON} mt-2`}>
          Xóa số điện thoại
        </button>
      )}
      <Alert text={error} />
      <Alert text={message} ok />
      {dialog}
    </div>
  );
}
