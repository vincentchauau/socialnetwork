"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
import BiometricCapture from "./BiometricCapture";
import TotpLoginForm from "./TotpLoginForm";
import { CARD, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { LivenessSetting, MfaChallenge, MfaFactor, loginWithBiometrics } from "../lib/auth";
import { goTo, postLoginTarget } from "../lib/navigate";

const FACTOR_LABEL: Record<MfaFactor, string> = {
  totp: "Ứng dụng xác thực",
  biometric: "Sinh trắc học",
};

function BiometricForm({ mfaToken, liveness, onCancel }: { mfaToken: string; liveness?: LivenessSetting; onCancel: () => void }) {
  const [audio, setAudio] = useState<Blob>();
  const [video, setVideo] = useState<Blob>();
  const [livenessToken, setLivenessToken] = useState<string>();
  const { busy, error, run } = useAction();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (await run(async () => void (await loginWithBiometrics(mfaToken, audio, video, livenessToken)))) {
      goTo(postLoginTarget());
    }
  }

  return (
    <form onSubmit={submit} aria-label="Xác minh danh tính">
      <p className="text-sm text-gray-600 mb-2">
        Quay một đoạn ngắn (nhìn camera và nói vài câu) để hoàn tất đăng nhập.
      </p>
      <BiometricCapture
        disabled={busy}
        liveness={liveness}
        onVideo={(blob, token) => {
          setVideo(blob);
          setLivenessToken(token);
        }}
        onAudio={setAudio}
      />
      <button type="submit" disabled={busy || (!audio && !video)} className={PRIMARY_BUTTON}>
        {busy ? "Đang xử lý..." : "Xác minh và đăng nhập"}
      </button>
      <button type="button" disabled={busy} onClick={onCancel} className={`${SECONDARY_BUTTON} mt-2`}>
        Hủy
      </button>
      <Alert text={error} />
    </form>
  );
}

/** Bước xác minh thêm sau khi mật khẩu/Google đúng: chỉ cần MỘT trong các cách mà tài khoản đã bật. */
export default function MfaStep({
  challenge,
  liveness,
  onCancel,
}: {
  challenge: MfaChallenge;
  liveness?: LivenessSetting;
  onCancel: () => void;
}) {
  const { mfaToken, factors } = challenge;
  const [factor, setFactor] = useState<MfaFactor>(factors[0]);
  const several = factors.length > 1;
  const finish = () => goTo(postLoginTarget());

  return (
    <main className={CARD}>
      <h1 className="text-2xl font-bold mb-4">Xác minh danh tính</h1>
      {several && (
        <div role="tablist" aria-label="Chọn cách xác minh" className="flex gap-2 mb-4">
          {factors.map((item) => (
            <button key={item} type="button" role="tab" id={`mfa-tab-${item}`} aria-selected={factor === item}
                    aria-controls="mfa-panel" onClick={() => setFactor(item)}
                    className={`flex-1 border rounded px-2 py-1 ${factor === item ? "bg-blue-600 text-white" : ""}`}>
              {FACTOR_LABEL[item]}
            </button>
          ))}
        </div>
      )}
      <div id="mfa-panel" role={several ? "tabpanel" : undefined} aria-labelledby={several ? `mfa-tab-${factor}` : undefined}>
        {factor === "totp" ? (
          <>
            <TotpLoginForm key="totp" mfaToken={mfaToken} onDone={finish} />
            <button type="button" onClick={onCancel} className={`${SECONDARY_BUTTON} mt-2`}>Hủy</button>
          </>
        ) : (
          <BiometricForm key="biometric" mfaToken={mfaToken} liveness={liveness} onCancel={onCancel} />
        )}
      </div>
    </main>
  );
}
