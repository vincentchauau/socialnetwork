"use client";

import { useEffect, useState } from "react";

import MfaStep from "./MfaStep";
import TokenConfirm from "./TokenConfirm";
import { PRIMARY_BUTTON } from "./ui";
import { AuthConfig, MfaChallenge, NO_CONFIG, getAuthConfig, loginWithMagicLink } from "../lib/auth";
import { goTo, postLoginTarget } from "../lib/navigate";

/** Đăng nhập bằng liên kết trong email. Nếu cần xác minh thêm thì chuyển về /login kèm ghi chú. */
export default function MagicLoginView() {
  const [challenge, setChallenge] = useState<MfaChallenge | null>(null);
  const [config, setConfig] = useState<AuthConfig>(NO_CONFIG);

  useEffect(() => {
    // Only the biometric second factor needs the liveness setting: read it once the challenge exists.
    if (!challenge) return;
    getAuthConfig().then(setConfig).catch(() => setConfig(NO_CONFIG));
  }, [challenge]);

  if (challenge) return <MfaStep challenge={challenge} liveness={config} onCancel={() => goTo("/login")} />;

  return (
    <TokenConfirm
      title="Đăng nhập bằng email"
      intro="Bấm nút bên dưới để hoàn tất đăng nhập."
      button="Đăng nhập"
      missing="Liên kết không hợp lệ hoặc đã hết hạn."
      confirm={async (token) => {
        const result = await loginWithMagicLink(token);
        if (result.kind === "mfa") setChallenge({ mfaToken: result.mfaToken, factors: result.factors });
        else goTo(postLoginTarget());
      }}
      success={<p role="status" className="text-sm text-green-700 mb-2">Đang chuyển hướng...</p>}
      failure={
        <>
          <p role="alert" className="text-sm text-red-600 mb-2">Liên kết không hợp lệ hoặc đã hết hạn.</p>
          <a href="/login" className={`${PRIMARY_BUTTON} block text-center`}>Về trang đăng nhập</a>
        </>
      }
    />
  );
}
