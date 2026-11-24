"use client";

import { useEffect, useState } from "react";

import AuthPanel from "./AuthPanel";
import MfaStep from "./MfaStep";
import { AuthConfig, MfaChallenge, NO_CONFIG, getAuthConfig } from "../lib/auth";
import { useSession } from "@sn/lib/useSession";
import { tr } from "../i18n";

/**
 * /login, the one screen of Đăng ký, Đăng nhập and Cập nhật. A visitor who is signed in opens on "Cập nhật" (reached from
 * the greeting in the top bar); one who is not opens on "Đăng nhập" and is not offered "Cập nhật".
 */
export default function LoginFlow() {
  const [config, setConfig] = useState<AuthConfig>(NO_CONFIG);
  const [challenge, setChallenge] = useState<MfaChallenge | null>(null);
  const session = useSession();

  useEffect(() => {
    // Chỉ là tính năng tùy chọn: không đọc được cấu hình thì đăng nhập bằng mật khẩu vẫn dùng được.
    getAuthConfig().then(setConfig).catch(() => setConfig(NO_CONFIG));
  }, []);

  if (challenge) return <MfaStep challenge={challenge} liveness={config} onCancel={() => setChallenge(null)} />;
  // Wait for the session check: which mode opens depends on it.
  if (session.status === "loading") return <p role="status" className="text-center mt-10">{tr("dang_tai")}</p>;
  const signedIn = session.status === "signed-in";
  // The key: signing in remounts the panel, so it opens on the account screen (its mode is read once, at mount).
  return <AuthPanel key={signedIn ? "in" : "out"} config={config} onMfa={setChallenge} signedIn={signedIn} initialMode={signedIn ? "account" : "login"} />;
}
