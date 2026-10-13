"use client";

import { FormEvent, useState } from "react";

import { setCsrfToken } from "@sn/api";
import Alert from "./Alert";
import UsernameField from "./UsernameField";
import { INPUT, LABEL, NOTE, PRIMARY_BUTTON, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";
import { changeUsername, usernameProblem } from "../lib/auth";

export const USERNAME_NOTE =
  "Mỗi 30 ngày chỉ đổi được một lần. Tên cũ được giữ chỗ 30 ngày. Các phiên đăng nhập khác sẽ bị đăng xuất.";

interface Props {
  username: string;
  hasPassword: boolean;
  canRenameAfter: string | null;
  onDone: () => void | Promise<void>;
}

/** The date from which renaming is allowed again, or null when it is allowed now (or the date is unusable). */
function futureDate(iso: string | null): Date | null {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) || date.getTime() <= Date.now() ? null : date;
}

export default function ChangeUsername({ username, hasPassword, canRenameAfter, onDone }: Props) {
  const [next, setNext] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, message, run, fail } = useAction();
  const { withReauth, dialog } = useReauth();
  const waitUntil = futureDate(canRenameAfter);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const name = next.trim();
    const problem = usernameProblem(name);
    if (problem) return fail(problem);
    const ok = await run(() =>
      withReauth(async () => {
        const session = await changeUsername(name, hasPassword ? password : undefined);
        setCsrfToken(session.csrf_token);
        return "Đã đổi tên đăng nhập.";
      }),
    );
    setPassword("");
    if (ok) {
      setNext("");
      await onDone();
    }
  }

  return (
    <form onSubmit={submit} aria-label="Đổi tên đăng nhập" className={SECTION}>
      <h2 className="font-bold mb-1">Tên đăng nhập</h2>
      <p className="mb-1">Hiện tại: <strong>{username}</strong></p>
      <p className={NOTE}>{USERNAME_NOTE}</p>
      {waitUntil && <p role="note" className="text-sm font-medium mb-2">Có thể đổi lại từ {waitUntil.toLocaleDateString("vi-VN")}</p>}
      <fieldset disabled={busy || waitUntil !== null} className="border-0 p-0 m-0">
        <UsernameField value={next} onChange={setNext} />
        {hasPassword && (
          <>
            <label htmlFor="rename-password" className={LABEL}>Mật khẩu hiện tại (để đổi tên)</label>
            <input id="rename-password" type="password" value={password} autoComplete="current-password" required
                   onChange={(e) => setPassword(e.target.value)} className={INPUT} />
          </>
        )}
        <button type="submit" className={PRIMARY_BUTTON}>{busy ? "Đang lưu..." : "Đổi tên"}</button>
      </fieldset>
      <Alert text={error} />
      <Alert text={message} ok />
      {dialog}
    </form>
  );
}
