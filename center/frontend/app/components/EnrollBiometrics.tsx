"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
import BiometricCapture from "./BiometricCapture";
import { INPUT, LABEL, PRIMARY_BUTTON, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { enrollBiometrics } from "../lib/auth";

interface Props {
  hasPassword: boolean;
  hasAudio: boolean;
  hasFace: boolean;
  onDone: () => void | Promise<void>;
}

/** Thêm hoặc thay giọng nói/khuôn mặt cho tài khoản đã đăng ký (kể cả tài khoản Google). */
export default function EnrollBiometrics({ hasPassword, hasAudio, hasFace, onDone }: Props) {
  const [audio, setAudio] = useState<Blob>();
  const [video, setVideo] = useState<Blob>();
  const [password, setPassword] = useState("");
  const [captureKey, setCaptureKey] = useState(0);
  const { busy, error, message, run, fail } = useAction();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!audio && !video) {
      return fail("Hãy quay khuôn mặt + giọng nói (hoặc ghi giọng nói riêng) trước khi lưu");
    }
    const ok = await run(async () => {
      const status = await enrollBiometrics(hasPassword ? password : undefined, audio, video);
      return status.passwordless_ready
        ? "Đã lưu. Đã có đủ giọng nói và khuôn mặt: bạn có thể bật đăng nhập không mật khẩu ở bên dưới."
        : "Đã lưu. Đăng nhập không mật khẩu cần cả giọng nói và khuôn mặt, hãy quay bổ sung phần còn thiếu.";
    });
    if (ok) {
      setAudio(undefined);
      setVideo(undefined);
      setPassword("");
      setCaptureKey((key) => key + 1); // xóa bản xem trước cũ
      await onDone();
    }
  }

  return (
    <form onSubmit={submit} aria-label="Thêm giọng nói hoặc khuôn mặt" className={SECTION}>
      <h2 className="font-bold mb-1">{hasAudio || hasFace ? "Đổi giọng nói / khuôn mặt" : "Thêm giọng nói / khuôn mặt"}</h2>
      <p className="text-sm text-gray-600 mb-3">
        Tùy chọn, không phải bước xác minh thêm: đăng nhập bằng mật khẩu hoặc Google vẫn vào thẳng. Dữ liệu này chỉ dùng
        để đăng nhập không mật khẩu, và chỉ dùng được khi đã lưu cả giọng nói và khuôn mặt (có thể lưu từng phần, quay
        bổ sung sau). Quay một lần, nhìn camera và nói vài câu. Đã lưu: giọng nói {hasAudio ? "có" : "chưa"}, khuôn mặt{" "}
        {hasFace ? "có" : "chưa"}.
      </p>
      <BiometricCapture key={captureKey} disabled={busy} onVideo={setVideo} onAudio={setAudio} />
      {hasPassword && (
        <>
          <label htmlFor="enroll-password" className={LABEL}>Nhập lại mật khẩu để xác nhận</label>
          <input id="enroll-password" type="password" value={password} autoComplete="current-password" required
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </>
      )}
      <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
        {busy ? "Đang lưu..." : "Lưu dữ liệu sinh trắc"}
      </button>
      <Alert text={error} />
      <Alert text={message} ok />
    </form>
  );
}
