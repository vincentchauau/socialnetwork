"use client";

import { useEffect, useState } from "react";

import MfaStep from "./MfaStep";
import TokenConfirm from "./TokenConfirm";
import { PRIMARY_BUTTON } from "./ui";
import { AuthConfig, MfaChallenge, NO_CONFIG, getAuthConfig, loginWithMagicLink } from "../lib/auth";
import { goTo, postLoginTarget } from "../lib/navigate";
import { tr } from "../i18n";
import Link from "next/link";

/** Đăng nhập bằng liên kết trong email. Nếu cần xác minh thêm thì chuyển về /login kèm ghi chú. */
export default function MagicLoginView() {
  const [challenge, setChallenge] = useState<MfaChallenge | null>(null);
  const [config, setConfig] = useState<AuthConfig>(NO_CONFIG);

  useEffect(() => {
    // Only the biometric second factor needs the liveness setting: read it once the challenge exists.
    if (!challenge) return;
    getAuthConfig().then(setConfig).catch(() => setConfig(NO_CONFIG));
  }, [challenge]);

  if (challenge) return <MfaStep challenge={challenge} liveness={config} onCancel={() => goTo("/user")} />;

  return (
    <TokenConfirm
      title={tr("dang_nhap_bang_email")}
      intro={tr("bam_nut_ben_duoi_de_hoan")}
      button={tr("dang_nhap")}
      missing={tr("lien_ket_khong_hop_le_hoac")}
      confirm={async (token) => {
        const result = await loginWithMagicLink(token);
        if (result.kind === "mfa") setChallenge({ mfaToken: result.mfaToken, factors: result.factors });
        else goTo(postLoginTarget());
      }}
      success={<p role="status" className="text-sm text-line mb-2">{tr("dang_chuyen_huong")}</p>}
      failure={
        <>
          <p role="alert" className="text-sm text-line mb-2">{tr("lien_ket_khong_hop_le_hoac")}</p>
          <Link href="/user" className={`${PRIMARY_BUTTON} block text-center`}>{tr("ve_trang_dang_nhap")}</Link>
        </>
      }
    />
  );
}
