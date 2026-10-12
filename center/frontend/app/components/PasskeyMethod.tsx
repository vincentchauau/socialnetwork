"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
import { INPUT, LABEL, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { usePasskeySupport } from "../hooks/usePasskeySupport";
import { MAX_PASSKEYS, PASSKEY_LIMIT_MESSAGE, PasskeyItem, addPasskey, deletePasskey, myPasskeyOptions, renamePasskey } from "../lib/auth";
import { PASSKEY_UNSUPPORTED, createPasskeyCredential } from "../lib/passkey";

interface Props {
  passkeys: PasskeyItem[];
  hasPassword: boolean;
  onDone: () => void | Promise<void>;
}

export const DEFAULT_PASSKEY_NAME = "Passkey của tôi";

const formatDate = (iso: string) => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString("vi-VN");
};

/** Đổi tên tại chỗ một Passkey. */
function PasskeyRow({ item, hasPassword, onDone }: { item: PasskeyItem; hasPassword: boolean; onDone: Props["onDone"] }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(item.name);
  const [confirming, setConfirming] = useState(false);
  const [password, setPassword] = useState("");
  const { busy, error, run, fail } = useAction();

  async function rename(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return fail("Hãy nhập tên cho Passkey");
    if (await run(async () => void (await renamePasskey(item.id, name.trim())))) {
      setEditing(false);
      await onDone();
    }
  }

  async function remove(event: FormEvent) {
    event.preventDefault();
    if (hasPassword && !password) return fail("Hãy nhập mật khẩu để xác nhận");
    if (await run(async () => void (await deletePasskey(item.id, hasPassword ? password : undefined)))) {
      setPassword("");
      setConfirming(false);
      await onDone();
    }
  }

  return (
    <li className="border-t first:border-t-0 py-2 text-sm">
      {editing ? (
        <form onSubmit={rename} aria-label={`Đổi tên ${item.name}`}>
          <label htmlFor={`passkey-name-${item.id}`} className={LABEL}>Tên mới</label>
          <input id={`passkey-name-${item.id}`} value={name} maxLength={64} onChange={(e) => setName(e.target.value)} className={INPUT} />
          <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>Lưu tên</button>
          <button type="button" disabled={busy} onClick={() => { setEditing(false); setName(item.name); }} className={`${SECONDARY_BUTTON} mt-2`}>
            Hủy
          </button>
        </form>
      ) : (
        <>
          <p className="font-medium">
            {item.name}
            {item.backed_up && <span className="ml-2 text-xs font-normal text-gray-600" title="Được đồng bộ giữa các thiết bị">(đã đồng bộ)</span>}
          </p>
          <p className="text-xs text-gray-600">
            Tạo ngày {formatDate(item.created_at)} · {item.last_used_at ? `Dùng lần cuối ${formatDate(item.last_used_at)}` : "Chưa dùng"}
          </p>
          <div className="flex gap-3 mt-1">
            <button type="button" className="text-blue-700 underline" disabled={busy} onClick={() => setEditing(true)}>Đổi tên</button>
            <button type="button" className="text-red-700 underline" disabled={busy} onClick={() => setConfirming(true)}>Xóa</button>
          </div>
        </>
      )}
      {confirming && (
        <form onSubmit={remove} aria-label={`Xóa ${item.name}`} className="mt-2">
          {hasPassword && (
            <>
              <label htmlFor={`passkey-del-${item.id}`} className={LABEL}>Nhập lại mật khẩu để xóa</label>
              <input id={`passkey-del-${item.id}`} type="password" value={password} autoComplete="current-password"
                     onChange={(e) => setPassword(e.target.value)} className={INPUT} />
            </>
          )}
          <button type="submit" disabled={busy} className={SECONDARY_BUTTON}>{busy ? "Đang xử lý..." : "Xác nhận xóa"}</button>
          <button type="button" disabled={busy} onClick={() => { setConfirming(false); setPassword(""); fail(""); }} className={`${SECONDARY_BUTTON} mt-2`}>
            Hủy
          </button>
        </form>
      )}
      <Alert text={error} />
    </li>
  );
}

/** Danh sách và quản lý Passkey của tài khoản: thêm, đổi tên, xóa (luôn phải còn ít nhất một cách đăng nhập). */
export default function PasskeyMethod({ passkeys, hasPassword, onDone }: Props) {
  const supported = usePasskeySupport();
  const [name, setName] = useState(DEFAULT_PASSKEY_NAME);
  const [password, setPassword] = useState("");
  const { busy, error, message, run, fail } = useAction();

  const full = passkeys.length >= MAX_PASSKEYS;

  async function add(event: FormEvent) {
    event.preventDefault();
    if (full) return;
    if (hasPassword && !password) return fail("Hãy nhập mật khẩu để xác nhận");
    const ok = await run(async () => {
      const { options, challenge_token } = await myPasskeyOptions(hasPassword ? password : undefined);
      const credential = await createPasskeyCredential(options);
      await addPasskey(credential, challenge_token, name);
      return "Đã thêm Passkey.";
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
        <ul aria-label="Passkey đã đăng ký" className="mb-2">
          {passkeys.map((item) => (
            <PasskeyRow key={item.id} item={item} hasPassword={hasPassword} onDone={onDone} />
          ))}
        </ul>
      )}
      <p className="text-xs text-gray-600 mb-1">Không cần tên đăng nhập. Thiết bị tự xử lý vân tay, Face ID hoặc Windows Hello.</p>
      {!supported && <p role="note" className="text-sm text-red-600 mb-1">{PASSKEY_UNSUPPORTED}</p>}
      {full && <p role="note" className="text-sm text-amber-800 mb-1">{PASSKEY_LIMIT_MESSAGE}</p>}
      <form onSubmit={add} aria-label="Thêm Passkey">
        <label htmlFor="passkey-new-name" className={LABEL}>Tên Passkey (không bắt buộc)</label>
        <input id="passkey-new-name" value={name} maxLength={64} disabled={full} onChange={(e) => setName(e.target.value)} className={INPUT} />
        {hasPassword && (
          <>
            <label htmlFor="passkey-password" className={LABEL}>Nhập lại mật khẩu để xác nhận</label>
            <input id="passkey-password" type="password" value={password} autoComplete="current-password" disabled={full}
                   onChange={(e) => setPassword(e.target.value)} className={INPUT} />
          </>
        )}
        <button type="submit" disabled={busy || !supported || full} className={PRIMARY_BUTTON}>
          {busy ? "Đang xử lý..." : "Thêm Passkey"}
        </button>
        <Alert text={error} />
        <Alert text={message} ok />
      </form>
    </div>
  );
}
