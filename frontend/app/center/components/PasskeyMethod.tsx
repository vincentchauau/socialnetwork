"use client";

import { FormEvent, useState } from "react";

import Alert from "@sn/elements/Alert";
import { INPUT, LABEL, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";
import { usePasskeySupport } from "../hooks/usePasskeySupport";
import { MAX_PASSKEYS, PASSKEY_LIMIT_MESSAGE, PasskeyItem, addPasskey, deletePasskey, myPasskeyOptions, renamePasskey } from "../lib/auth";
import { PASSKEY_UNSUPPORTED, createPasskeyCredential } from "../lib/passkey";
import Button from "@sn/elements/Button";
import { usePasswordProof } from "./PasswordConfirm";
import { tr } from "../i18n";
import { intlLocale } from "@sn/lib/i18n";
import TextBox from "@sn/elements/TextBox";

interface Props {
  passkeys: PasskeyItem[];
  hasPassword: boolean;
  onDone: () => void | Promise<void>;
}

const DEFAULT_PASSKEY_NAME = tr("passkey_cua_toi");

const formatDate = (iso: string) => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString(intlLocale());
};

/** Đổi tên tại chỗ một Passkey. */
function PasskeyRow({ item, hasPassword, onDone }: { item: PasskeyItem; hasPassword: boolean; onDone: Props["onDone"] }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(item.name);
  const [confirming, setConfirming] = useState(false);
  const { password, setPassword, isShared } = usePasswordProof();
  const { busy, error, run, fail } = useAction();
  const { withReauth, dialog } = useReauth();

  async function rename(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return fail(tr("hay_nhap_ten_cho_passkey"));
    if (await run(async () => void (await renamePasskey(item.id, name.trim())))) {
      setEditing(false);
      await onDone();
    }
  }

  async function remove(event: FormEvent) {
    event.preventDefault();
    if (hasPassword && !password) return fail(tr("hay_nhap_mat_khau_de_xac"));
    if (await run(() => withReauth(async () => void (await deletePasskey(item.id, hasPassword ? password : undefined))))) {
      setPassword("");
      setConfirming(false);
      await onDone();
    }
  }

  return (
    <li className="border-t first:border-t-0 py-2 text-sm">
      {editing ? (
        <form onSubmit={rename} aria-label={tr("doi_ten_p0", { p0: item.name })}>
          <label htmlFor={`passkey-name-${item.id}`} className={LABEL}>{tr("ten_moi")}</label>
          <TextBox id={`passkey-name-${item.id}`} value={name} maxLength={64} onChange={(e) => setName(e.target.value)} className={INPUT} />
          <Button type="submit" disabled={busy} className={PRIMARY_BUTTON}>{tr("luu_ten")}</Button>
          <Button variant="secondary" type="button" disabled={busy} onClick={() => { setEditing(false); setName(item.name); }} className={`${SECONDARY_BUTTON} mt-2`}>
            {tr("huy")}
          </Button>
        </form>
      ) : (
        <>
          <p className="font-medium">
            {item.name}
            {item.backed_up && <span className="ml-2 text-xs font-normal text-line" title={tr("duoc_dong_bo_giua_cac_thiet")}>{tr("da_dong_bo")}</span>}
          </p>
          <p className="text-xs text-line">
            {tr("tao_ngay")} {formatDate(item.created_at)} · {item.last_used_at ? tr("dung_lan_cuoi_p0", { p0: formatDate(item.last_used_at) }) : tr("chua_dung")}
          </p>
          <div className="flex gap-3 mt-1">
            <Button type="button" className="text-line underline" disabled={busy} onClick={() => setEditing(true)}>{tr("doi_ten")}</Button>
            <Button type="button" className="text-line underline" disabled={busy} onClick={() => setConfirming(true)}>{tr("xoa")}</Button>
          </div>
        </>
      )}
      {confirming && (
        <form onSubmit={remove} aria-label={tr("xoa_p0", { p0: item.name })} className="mt-2">
          {hasPassword && !isShared && (
            <>
              <label htmlFor={`passkey-del-${item.id}`} className={LABEL}>{tr("nhap_lai_mat_khau_de_xoa")}</label>
              <TextBox id={`passkey-del-${item.id}`} type="password" value={password} autoComplete="current-password"
                     onChange={(e) => setPassword(e.target.value)} className={INPUT} />
            </>
          )}
          <Button variant="secondary" type="submit" disabled={busy} className={SECONDARY_BUTTON}>{busy ? tr("dang_xu_ly") : tr("xac_nhan_xoa")}</Button>
          <Button variant="secondary" type="button" disabled={busy} onClick={() => { setConfirming(false); setPassword(""); fail(""); }} className={`${SECONDARY_BUTTON} mt-2`}>
            {tr("huy")}
          </Button>
        </form>
      )}
      <Alert className="mt-2">{error}</Alert>
      {dialog}
    </li>
  );
}

/** Danh sách và quản lý Passkey của tài khoản: thêm, đổi tên, xóa (luôn phải còn ít nhất một cách đăng nhập). */
export default function PasskeyMethod({ passkeys, hasPassword, onDone }: Props) {
  const supported = usePasskeySupport();
  const [name, setName] = useState(DEFAULT_PASSKEY_NAME);
  const { password, setPassword, isShared } = usePasswordProof();
  const { busy, error, message, run, fail } = useAction();
  const { withReauth, dialog } = useReauth();

  const full = passkeys.length >= MAX_PASSKEYS;

  async function add(event: FormEvent) {
    event.preventDefault();
    if (full) return;
    if (hasPassword && !password) return fail(tr("hay_nhap_mat_khau_de_xac"));
    const ok = await run(async () => {
      const { options, challenge_token } = await withReauth(() => myPasskeyOptions(hasPassword ? password : undefined));
      const credential = await createPasskeyCredential(options);
      await withReauth(() => addPasskey(credential, challenge_token, name));
      return tr("da_them_passkey");
    });
    setPassword("");
    if (ok) {
      setName(DEFAULT_PASSKEY_NAME);
      await onDone();
    }
  }

  return (
    <div className="mt-2">
      {passkeys.length > 0 && (
        <ul aria-label={tr("passkey_da_dang_ky")} className="mb-2">
          {passkeys.map((item) => (
            <PasskeyRow key={item.id} item={item} hasPassword={hasPassword} onDone={onDone} />
          ))}
        </ul>
      )}
      <p className="text-xs text-line mb-1">{tr("khong_can_ten_dang_nhap_thiet")}</p>
      {!supported && <p role="note" className="text-sm text-line mb-1">{PASSKEY_UNSUPPORTED}</p>}
      {full && <p role="note" className="text-sm text-line mb-1">{PASSKEY_LIMIT_MESSAGE}</p>}
      <form onSubmit={add} aria-label={tr("them_passkey")}>
        <label htmlFor="passkey-new-name" className={LABEL}>{tr("ten_passkey_khong_bat_buoc")}</label>
        <TextBox id="passkey-new-name" value={name} maxLength={64} disabled={full} onChange={(e) => setName(e.target.value)} className={INPUT} />
        {hasPassword && !isShared && (
          <>
            <label htmlFor="passkey-password" className={LABEL}>{tr("nhap_lai_mat_khau_de_xac")}</label>
            <TextBox id="passkey-password" type="password" value={password} autoComplete="current-password" disabled={full}
                   onChange={(e) => setPassword(e.target.value)} className={INPUT} />
          </>
        )}
        <Button type="submit" disabled={busy || !supported || full} className={PRIMARY_BUTTON}>
          {busy ? tr("dang_xu_ly") : tr("them_passkey")}
        </Button>
        <Alert className="mt-2">{error}</Alert>
        <Alert tone="success" className="mt-2">{message}</Alert>
      </form>
      {dialog}
    </div>
  );
}
