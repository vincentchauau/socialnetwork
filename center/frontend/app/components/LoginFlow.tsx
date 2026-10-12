"use client";

import { FormEvent, useEffect, useState } from "react";

import Alert from "./Alert";
import BiometricCapture from "./BiometricCapture";
import RegisterForm from "./RegisterForm";
import SignInForm from "./SignInForm";
import { CARD, LINK_BUTTON, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { AuthConfig, getAuthConfig, loginWithBiometrics } from "../lib/auth";
import { goTo, postLoginTarget } from "../lib/navigate";

type Mode = "login" | "register";

const NO_CONFIG: AuthConfig = { google_client_id: null, biometrics_enabled: false };

/** Bước xác minh thêm (tùy chọn) sau khi mật khẩu/Google đúng và tài khoản đã bật yêu cầu này. */
function MfaStep({ mfaToken, onCancel }: { mfaToken: string; onCancel: () => void }) {
  const [audio, setAudio] = useState<Blob>();
  const [video, setVideo] = useState<Blob>();
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (await run(async () => void (await loginWithBiometrics(mfaToken, audio, video)))) {
      goTo(postLoginTarget());
    }
  }

  return (
    <main className={CARD}>
      <h1 className="text-2xl font-bold mb-4">Xác minh danh tính</h1>
      <form onSubmit={submit} aria-label="Xác minh danh tính">
        <p className="text-sm text-gray-600 mb-2">
          Quay một đoạn ngắn (nhìn camera và nói vài câu) để hoàn tất đăng nhập.
        </p>
        <BiometricCapture disabled={busy} onVideo={setVideo} onAudio={setAudio} />
        <button type="submit" disabled={busy || (!audio && !video)} className={PRIMARY_BUTTON}>
          {busy ? "Đang xử lý..." : "Xác minh và đăng nhập"}
        </button>
        <button type="button" disabled={busy} onClick={onCancel} className={`${SECONDARY_BUTTON} mt-2`}>
          Hủy
        </button>
        <Alert text={error} />
      </form>
    </main>
  );
}

export default function LoginFlow() {
  const [config, setConfig] = useState<AuthConfig>(NO_CONFIG);
  const [mode, setMode] = useState<Mode>("login");
  const [mfaToken, setMfaToken] = useState<string | null>(null);

  useEffect(() => {
    // Chỉ là tính năng tùy chọn: không đọc được cấu hình thì đăng nhập bằng mật khẩu vẫn dùng được.
    getAuthConfig().then(setConfig).catch(() => setConfig(NO_CONFIG));
  }, []);

  if (mfaToken) return <MfaStep mfaToken={mfaToken} onCancel={() => setMfaToken(null)} />;

  const title = mode === "login" ? "Đăng nhập" : "Đăng ký";
  return (
    <main className={CARD}>
      <h1 className="text-2xl font-bold mb-4">{title}</h1>
      {/* key: đổi chế độ thì dựng lại form, xóa mọi dữ liệu và bản ghi cũ */}
      {mode === "login" ? (
        <SignInForm key="login" config={config} onMfa={setMfaToken} />
      ) : (
        <RegisterForm key="register" config={config} />
      )}
      <button type="button" className={LINK_BUTTON} onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "Chưa có tài khoản? Đăng ký" : "Đã có tài khoản? Đăng nhập"}
      </button>
    </main>
  );
}
