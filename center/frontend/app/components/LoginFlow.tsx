"use client";

import { useEffect, useState } from "react";

import MfaStep from "./MfaStep";
import RegisterForm from "./RegisterForm";
import SignInForm from "./SignInForm";
import { CARD, LINK_BUTTON } from "./ui";
import { AuthConfig, MfaChallenge, NO_CONFIG, getAuthConfig } from "../lib/auth";

type Mode = "login" | "register";



export default function LoginFlow() {
  const [config, setConfig] = useState<AuthConfig>(NO_CONFIG);
  const [mode, setMode] = useState<Mode>("login");
  const [challenge, setChallenge] = useState<MfaChallenge | null>(null);

  useEffect(() => {
    // Chỉ là tính năng tùy chọn: không đọc được cấu hình thì đăng nhập bằng mật khẩu vẫn dùng được.
    getAuthConfig().then(setConfig).catch(() => setConfig(NO_CONFIG));
  }, []);

  if (challenge) return <MfaStep challenge={challenge} onCancel={() => setChallenge(null)} />;

  const title = mode === "login" ? "Đăng nhập" : "Đăng ký";
  return (
    <main className={CARD}>
      <h1 className="text-2xl font-bold mb-4">{title}</h1>
      {/* key: đổi chế độ thì dựng lại form, xóa mọi dữ liệu và bản ghi cũ */}
      {mode === "login" ? (
        <SignInForm key="login" config={config} onMfa={setChallenge} />
      ) : (
        <RegisterForm key="register" config={config} />
      )}
      <button type="button" className={LINK_BUTTON} onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "Chưa có tài khoản? Đăng ký" : "Đã có tài khoản? Đăng nhập"}
      </button>
    </main>
  );
}
