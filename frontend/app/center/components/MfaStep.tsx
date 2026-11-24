"use client";

import { FormEvent, useState } from "react";

import Alert from "@sn/elements/Alert";
import BiometricCapture from "./BiometricCapture";
import TotpLoginForm from "./TotpLoginForm";
import { CARD, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { LivenessSetting, MfaChallenge, MfaFactor, loginWithBiometrics } from "../lib/auth";
import { goTo, postLoginTarget } from "../lib/navigate";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";

const FACTOR_LABEL: Record<MfaFactor, string> = {
  get totp() { return tr("ung_dung_xac_thuc"); },
  get biometric() { return tr("sinh_trac_hoc"); },
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
    <form onSubmit={submit} aria-label={tr("xac_minh_danh_tinh")}>
      <p className="text-sm text-line mb-2">
        {tr("quay_mot_doan_ngan_nhin_camera")}
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
      <Button type="submit" disabled={busy || (!audio && !video)} className={PRIMARY_BUTTON}>
        {busy ? tr("dang_xu_ly") : tr("xac_minh_va_dang_nhap")}
      </Button>
      <Button variant="secondary" type="button" disabled={busy} onClick={onCancel} className={`${SECONDARY_BUTTON} mt-2`}>
        {tr("huy")}
      </Button>
      <Alert className="mt-2">{error}</Alert>
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
      <h1 className="text-2xl font-bold mb-4">{tr("xac_minh_danh_tinh")}</h1>
      {several && (
        <div role="tablist" aria-label={tr("chon_cach_xac_minh")} className="flex gap-2 mb-4">
          {factors.map((item) => (
            <Button key={item} type="button" role="tab" id={`mfa-tab-${item}`} aria-selected={factor === item}
                    aria-controls="mfa-panel" onClick={() => setFactor(item)}
                    className={`flex-1 rounded px-2 py-1 ${factor === item ? "bg-solid-2" : "bg-solid-1"}`}>
              {FACTOR_LABEL[item]}
            </Button>
          ))}
        </div>
      )}
      <div id="mfa-panel" role={several ? "tabpanel" : undefined} aria-labelledby={several ? `mfa-tab-${factor}` : undefined}>
        {factor === "totp" ? (
          <>
            <TotpLoginForm key="totp" mfaToken={mfaToken} onDone={finish} />
            <Button variant="secondary" type="button" onClick={onCancel} className={`${SECONDARY_BUTTON} mt-2`}>{tr("huy")}</Button>
          </>
        ) : (
          <BiometricForm key="biometric" mfaToken={mfaToken} liveness={liveness} onCancel={onCancel} />
        )}
      </div>
    </main>
  );
}
