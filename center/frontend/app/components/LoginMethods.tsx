"use client";

import { FormEvent, ReactNode, useState } from "react";

import Alert from "./Alert";
import BiometricMethod from "./BiometricMethod";
import { INPUT, LABEL, SECONDARY_BUTTON, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { AuthConfig, Me, unlinkGoogle } from "../lib/auth";

interface Props {
  me: Me;
  config: AuthConfig;
  onDone: () => void | Promise<void>;
}

function Row({ name, state, children }: { name: string; state: string; children?: ReactNode }) {
  return (
    <li className="border-t first:border-t-0 py-2">
      <p className="font-medium">
        {name}: <span className="font-normal">{state}</span>
      </p>
      {children}
    </li>
  );
}

const anchor = (href: string, text: string) => (
  <a href={href} className="text-sm text-blue-700 underline">{text}</a>
);

/** Hủy liên kết Google: chỉ khi tài khoản đã có mật khẩu (luôn còn một cách đăng nhập chính). */
function UnlinkGoogle({ hasPassword, onDone }: { hasPassword: boolean; onDone: Props["onDone"] }) {
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();

  if (!hasPassword) {
    return <p className="text-sm text-gray-600">Hãy đặt mật khẩu trước khi hủy liên kết Google.</p>;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (await run(async () => void (await unlinkGoogle(password)))) {
      setPassword("");
      await onDone();
    }
  }

  return (
    <form onSubmit={submit} aria-label="Hủy liên kết Google">
      <label htmlFor="unlink-google-password" className={LABEL}>Nhập lại mật khẩu để hủy liên kết</label>
      <input id="unlink-google-password" type="password" value={password} autoComplete="current-password" required
             onChange={(e) => setPassword(e.target.value)} className={INPUT} />
      <button type="submit" disabled={busy} className={SECONDARY_BUTTON}>
        {busy ? "Đang xử lý..." : "Hủy liên kết Google"}
      </button>
      <Alert text={error} />
    </form>
  );
}

/** Bốn cách đăng nhập của tài khoản; thêm/thay/hủy giọng nói và webcam ngay tại đây (luôn phải còn ít nhất một cách). */
export default function LoginMethods({ me, config, onDone }: Props) {
  const enrol = config.biometrics_enabled;
  return (
    <section aria-label="Các cách đăng nhập" className={SECTION}>
      <h2 className="font-bold mb-2">Các cách đăng nhập</h2>
      <ul>
        <Row name="Mật khẩu" state={me.has_password ? "đã đặt" : "chưa đặt"}>
          {anchor("#doi-mat-khau", me.has_password ? "Đổi mật khẩu" : "Đặt mật khẩu")}
        </Row>
        <Row name="Google" state={me.google_linked ? `đã liên kết với ${me.email ?? "tài khoản Google"}` : "chưa liên kết"}>
          {me.google_linked && <UnlinkGoogle hasPassword={me.has_password} onDone={onDone} />}
          {!me.google_linked && config.google_client_id && anchor("#lien-ket-google", "Liên kết Google")}
        </Row>
        {enrol && (
          <Row name="Giọng nói" state={me.voice_login ? "đã bật" : "chưa bật"}>
            <BiometricMethod kind="voice" enabled={me.voice_login} hasPassword={me.has_password} onDone={onDone} />
          </Row>
        )}
        {enrol && (
          <Row name="Webcam" state={me.webcam_login ? "đã bật" : "chưa bật"}>
            <BiometricMethod kind="webcam" enabled={me.webcam_login} hasPassword={me.has_password} onDone={onDone} />
          </Row>
        )}
      </ul>
    </section>
  );
}
