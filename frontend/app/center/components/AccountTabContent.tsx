"use client";

import { FormEvent, ReactNode, useState } from "react";

import Alert from "@sn/elements/Alert";
import Biometric2faToggle from "./Biometric2faToggle";
import BiometricMethod from "./BiometricMethod";
import EmailMethod from "./EmailMethod";
import LinkGoogle from "./LinkGoogle";
import PasskeyMethod from "./PasskeyMethod";
import PasswordForm from "./PasswordForm";
import PhoneMethod from "./PhoneMethod";
import QrMethod from "./QrMethod";
import SessionsMethod from "./SessionsMethod";
import TotpMethod from "./TotpMethod";
import { INPUT, LABEL, SECONDARY_BUTTON, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";
import { AuthConfig, Me, logout, unlinkGoogle } from "../lib/auth";
import type { AuthTab } from "../lib/authTabs";
import { goTo } from "../lib/navigate";
import Button from "@sn/elements/Button";
import { usePasswordProof } from "./PasswordConfirm";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

interface Props {
  tab: AuthTab;
  me: Me;
  config: AuthConfig;
  onDone: () => void | Promise<void>;
  /** The recovery codes just made, shown once in the recovery-codes tab. */
  codes: string[] | null;
  onCodes: (codes: string[] | null) => void;
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

const NO_USERNAME = tr("dang_nhap_khong_can_ten_dang");

const phoneState = (me: Me) => (me.phone ? `${me.phone} (${me.phone_verified ? tr("da_xac_minh") : tr("chua_xac_minh")})` : tr("chua_co"));

/** Hủy liên kết Google: chỉ khi tài khoản đã có mật khẩu (luôn còn một cách đăng nhập chính). */
function UnlinkGoogle({ hasPassword, onDone }: { hasPassword: boolean; onDone: () => void | Promise<void> }) {
  const { password, setPassword, isShared } = usePasswordProof();
  const { busy, error, run } = useAction();
  const { withReauth, dialog } = useReauth();

  if (!hasPassword) {
    return <p className="text-sm text-line">{tr("hay_dat_mat_khau_truoc_khi")}</p>;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (await run(() => withReauth(async () => void (await unlinkGoogle(password))))) {
      setPassword("");
      await onDone();
    }
  }

  return (
    <form onSubmit={submit} aria-label={tr("huy_lien_ket_google")}>
      {!isShared && (
        <>
          <label htmlFor="unlink-google-password" className={LABEL}>{tr("nhap_lai_mat_khau_de_huy")}</label>
          <TextBox id="unlink-google-password" type="password" value={password} autoComplete="current-password" required
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </>
      )}
      <Button variant="secondary" type="submit" disabled={busy} className={SECONDARY_BUTTON}>
        {busy ? tr("dang_xu_ly") : tr("huy_lien_ket_google")}
      </Button>
      <Alert className="mt-2">{error}</Alert>
      {dialog}
    </form>
  );
}

/** "Đăng xuất mọi nơi": ends every session of the account, this one included. */
function SignOutEverywhere() {
  const signOut = useAction();
  return (
    <div className="mt-2">
      <Button
        type="button"
        disabled={signOut.busy}
        className="w-full bg-solid-1 text-line px-4 py-2 rounded disabled:opacity-50"
        onClick={async () => {
          if (await signOut.run(logout)) goTo("/user");
        }}
      >
        {tr("dang_xuat_moi_noi")}
      </Button>
      <Alert className="mt-2">{signOut.error}</Alert>
    </div>
  );
}

/** One list card per method, so a tab holds exactly its own state line and its own controls. */
function Card({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section aria-label={label} className={SECTION}>
      <ul>{children}</ul>
    </section>
  );
}

/** The content of one tab of the account page: the method's state and the forms that change it. */
export default function AccountTabContent({ tab, me, config, onDone, codes, onCodes }: Props) {
  switch (tab) {
    case "password":
      return (
        <>
          <Card label={tr("mat_khau")}>
            <Row name={tr("mat_khau")} state={me.has_password ? tr("da_dat") : tr("chua_dat")} />
          </Card>
          <div id="doi-mat-khau">
            <PasswordForm hasPassword={me.has_password} onDone={onDone} />
          </div>
        </>
      );
    case "webcam":
      return (
        <>
          <Card label={tr("webcam_khuon_mat")}>
            <Row name={tr("webcam_khuon_mat")} state={me.webcam_login ? tr("da_bat") : tr("chua_bat")}>
              {me.webcam_login && <p className="text-xs text-line">{NO_USERNAME}</p>}
              <BiometricMethod kind="webcam" enabled={me.webcam_login} hasPassword={me.has_password} liveness={config} onDone={onDone} />
            </Row>
          </Card>
          <section aria-label={tr("bao_mat_nang_cao")} className="text-left mb-4">
            <h2 className="font-bold mb-2">{tr("bao_mat_nang_cao_tuy_chon")}</h2>
            <Biometric2faToggle
              enabled={me.require_biometric_2fa}
              hasPassword={me.has_password}
              ready={me.has_audio || me.has_face}
              onDone={onDone}
            />
          </section>
        </>
      );
    case "voice":
      return (
        <Card label={tr("giong_noi")}>
          <Row name={tr("giong_noi")} state={me.voice_login ? tr("da_bat") : tr("chua_bat")}>
            {me.voice_login && <p className="text-xs text-line">{NO_USERNAME}</p>}
            <BiometricMethod kind="voice" enabled={me.voice_login} hasPassword={me.has_password} onDone={onDone} />
          </Row>
        </Card>
      );
    case "totp":
    case "recovery":
      return (
        <TotpMethod
          part={tab}
          enabled={me.totp_enabled}
          recoveryCodesLeft={me.recovery_codes_left}
          hasPassword={me.has_password}
          codes={codes}
          onCodes={onCodes}
          onDone={onDone}
        />
      );
    case "email":
      return (
        <Card label="Email">
          <Row name="Email" state={me.email ? `${me.email} (${me.email_verified ? tr("da_xac_minh") : tr("chua_xac_minh")})` : tr("chua_co")}>
            <EmailMethod me={me} onDone={onDone} />
          </Row>
        </Card>
      );
    case "phone":
      return (
        <Card label="SMS">
          <Row name={tr("so_dien_thoai")} state={phoneState(me)}>
            <PhoneMethod me={me} onDone={onDone} />
          </Row>
        </Card>
      );
    case "google":
      return (
        <>
          <Card label="Google">
            <Row name="Google" state={me.google_linked ? tr("da_lien_ket_voi_p0", { p0: me.email ?? tr("tai_khoan_google") }) : tr("chua_lien_ket")}>
              {me.google_linked && <UnlinkGoogle hasPassword={me.has_password} onDone={onDone} />}
            </Row>
          </Card>
          {config.google_client_id && !me.google_linked && (
            <div id="lien-ket-google">
              <LinkGoogle clientId={config.google_client_id} hasPassword={me.has_password} onDone={onDone} />
            </div>
          )}
        </>
      );
    case "passkey": {
      const passkeys = me.passkeys ?? [];
      return (
        <Card label="Passkey">
          <Row name="Passkey" state={passkeys.length ? tr("p0_passkey_da_dang_ky", { p0: passkeys.length }) : tr("chua_co")}>
            {passkeys.length > 0 && <p className="text-xs text-line">{NO_USERNAME}</p>}
            <PasskeyMethod passkeys={passkeys} hasPassword={me.has_password} onDone={onDone} />
          </Row>
        </Card>
      );
    }
    case "qr":
      return <QrMethod />;
    case "username":
      return null; // not a tab: AccountMode draws it, with the password confirmation at its end
    case "sessions":
      return (
        <SessionsMethod>
          <SignOutEverywhere />
        </SessionsMethod>
      );
  }
}
