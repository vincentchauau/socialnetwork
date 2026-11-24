"use client";

import { FormEvent, useState } from "react";

import { useAccountChange } from "./AccountChanges";
import Alert from "@sn/elements/Alert";
import ApplyButton from "./ApplyButton";
import { INPUT, LABEL, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";
import { Me, PHONE_INVALID, PHONE_SMS_WARNING, isPhoneValid, removeMyPhone, setMyPhone, verifyMyPhone } from "../lib/auth";
import Button from "@sn/elements/Button";
import { usePasswordProof } from "./PasswordConfirm";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

interface Props {
  me: Me;
  onDone: () => void | Promise<void>;
}

/** Thêm/đổi số điện thoại, nhập mã SMS xác minh và xóa số. `Me` là nguồn sự thật, tải lại sau mỗi thay đổi. */
export default function PhoneMethod({ me, onDone }: Props) {
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const { password, setPassword, isShared } = usePasswordProof();
  const [awaitingCode, setAwaitingCode] = useState(false);
  const { busy, error, message, run, fail } = useAction();
  const { withReauth, dialog } = useReauth();
  const needsPassword = me.has_password;
  // The server stores a number only once it is verified, so `Me` never reports a pending one: remember it here.
  const unverified = awaitingCode || (Boolean(me.phone) && !me.phone_verified);

  /** Same code for the form's own button and for the page's "Đổi tài khoản": true when the SMS was sent. */
  async function apply(): Promise<boolean> {
    if (!isPhoneValid(phone)) {
      fail(PHONE_INVALID);
      return false;
    }
    const ok = await run(async () => {
      await withReauth(() => setMyPhone(phone, needsPassword ? password : undefined));
      return tr("chung_toi_da_gui_ma_xac_2");
    });
    if (!ok) return false;
    setPhone("");
    setPassword("");
    setAwaitingCode(true);
    await onDone();
    return true;
  }

  useAccountChange("cach-phone", "SMS", phone.trim() !== "", apply);

  function savePhone(event: FormEvent) {
    event.preventDefault();
    void apply();
  }

  async function verify(event: FormEvent) {
    event.preventDefault();
    if (!/^\d{6}$/.test(code.trim())) return fail(tr("ma_gom_6_chu_so"));
    const ok = await run(async () => {
      await verifyMyPhone(code);
      return tr("da_xac_minh_so_dien_thoai");
    });
    if (!ok) return;
    setCode("");
    setAwaitingCode(false);
    await onDone();
  }

  async function remove() {
    const ok = await run(async () => {
      await withReauth(() => removeMyPhone(needsPassword ? password : undefined));
      return tr("da_xoa_so_dien_thoai");
    });
    if (!ok) return;
    setPassword("");
    await onDone();
  }

  return (
    <div className="mt-1">
      <p role="note" className="text-xs text-line mb-2">{PHONE_SMS_WARNING}</p>
      {unverified && (
        <form onSubmit={verify} aria-label={tr("xac_minh_so_dien_thoai")}>
          <label htmlFor="phone-code" className={LABEL}>{tr("ma_sms_6_chu_so")}</label>
          <TextBox id="phone-code" value={code} inputMode="numeric" autoComplete="one-time-code" maxLength={6} required
                 onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className={INPUT} />
          <Button type="submit" disabled={busy} className={PRIMARY_BUTTON}>{tr("xac_minh_so")}</Button>
        </form>
      )}
      <form onSubmit={savePhone} aria-label={me.phone ? tr("doi_so_dien_thoai") : tr("them_so_dien_thoai")}>
        <label htmlFor="phone-new" className={LABEL}>{me.phone ? tr("so_dien_thoai_moi") : tr("so_dien_thoai")}</label>
        <TextBox id="phone-new" type="tel" value={phone} autoComplete="tel" inputMode="tel" placeholder="+84901234567" required
               onChange={(e) => setPhone(e.target.value)} className={INPUT} />
        <ApplyButton variant="secondary" disabled={busy} className={SECONDARY_BUTTON}>
          {me.phone ? tr("doi_so_dien_thoai") : tr("them_so_dien_thoai")}
        </ApplyButton>
      </form>
      {needsPassword && !isShared && (
        <div className="mt-2">
          <label htmlFor="phone-password" className={LABEL}>{tr("nhap_lai_mat_khau_de_xac")}</label>
          <TextBox id="phone-password" type="password" value={password} autoComplete="current-password"
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </div>
      )}
      {me.phone && (
        <Button variant="secondary" type="button" disabled={busy} onClick={() => void remove()} className={`${SECONDARY_BUTTON} mt-2`}>
          {tr("xoa_so_dien_thoai")}
        </Button>
      )}
      <Alert className="mt-2">{error}</Alert>
      <Alert tone="success" className="mt-2">{message}</Alert>
      {dialog}
    </div>
  );
}
