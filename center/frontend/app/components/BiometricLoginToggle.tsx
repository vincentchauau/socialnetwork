"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
import BiometricWarning from "./BiometricWarning";
import { INPUT, LABEL, NOTE, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { setBiometricLogin } from "../lib/auth";

interface Props {
  enabled: boolean;
  hasPassword: boolean;
  onDone: () => void | Promise<void>;
}

/** Bật/tắt đăng nhập chỉ bằng giọng nói + khuôn mặt. Chỉ hiện khi tài khoản đã lưu cả hai. */
export default function BiometricLoginToggle({ enabled, hasPassword, onDone }: Props) {
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent) {
    event.preventDefault();
    const ok = await run(async () => void (await setBiometricLogin(!enabled, hasPassword ? password : undefined)));
    if (ok) {
      setPassword("");
      await onDone();
    }
  }

  return (
    <form onSubmit={submit} aria-label="Đăng nhập chỉ bằng giọng nói và khuôn mặt" className={SECTION}>
      <h2 className="font-bold mb-1">
        Đăng nhập chỉ bằng giọng nói + khuôn mặt: {enabled ? "đang BẬT" : "đang tắt"}
      </h2>
      <p className={NOTE}>
        Tùy chọn, là một cách đăng nhập riêng: khi bật, bạn có thể đăng nhập chỉ bằng tên đăng nhập + khuôn mặt + giọng
        nói (để trống mật khẩu). Phải khớp cả hai, với ngưỡng nghiêm hơn, và bị khóa tạm sau nhiều lần sai. Có hay không
        bật, đăng nhập bằng mật khẩu vẫn đăng nhập bình thường.
      </p>
      <BiometricWarning />
      {hasPassword && (
        <>
          <label htmlFor="toggle-password" className={LABEL}>Nhập lại mật khẩu để xác nhận</label>
          <input id="toggle-password" type="password" value={password} autoComplete="current-password" required
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </>
      )}
      <button type="submit" disabled={busy}
              className={`w-full p-2 rounded font-bold text-white disabled:opacity-50 ${enabled ? "bg-gray-700" : "bg-blue-600"}`}>
        {busy ? "Đang lưu..." : enabled ? "Tắt đăng nhập chỉ bằng sinh trắc học" : "Bật đăng nhập chỉ bằng sinh trắc học"}
      </button>
      <Alert text={error} />
    </form>
  );
}
