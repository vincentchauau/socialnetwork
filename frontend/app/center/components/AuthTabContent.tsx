"use client";

import AudioRecord from "./AudioRecord";
import BiometricWarning from "./BiometricWarning";
import EmailLogin from "./EmailLogin";
import GoogleSignInButton from "./GoogleSignInButton";
import PasswordField from "./PasswordField";
import PhoneLogin from "./PhoneLogin";
import QrLogin from "./QrLogin";
import { TOTP_LENGTH, digitsOnly } from "./TotpLoginForm";
import UsernameField from "./UsernameField";
import VideoRecord from "./VideoRecord";
import { INPUT, LABEL } from "./ui";
import type { AuthFields } from "../hooks/useAuthFields";
import { AuthConfig, LoginResult, loginWithGoogle } from "../lib/auth";
import type { AuthTab, EntryMode } from "../lib/authTabs";
import { PASSKEY_UNSUPPORTED } from "../lib/passkey";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import Link from "next/link";
import TextBox from "@sn/elements/TextBox";

export type SignIn = (action: () => Promise<LoginResult | undefined>) => Promise<void>;

interface TabContentProps {
  tab: AuthTab;
  mode: EntryMode;
  config: AuthConfig;
  fields: AuthFields;
  busy: boolean;
  fail: (message: string) => void;
  signIn: SignIn;
  passkeySupported: boolean;
}

const PASSKEY_LOGIN_HINT = tr("dung_van_tay_face_id_windows");
const AUTO_HINT = {
  get voice() { return tr("he_thong_tu_nhan_ra_giong"); },
  get webcam() { return tr("he_thong_tu_nhan_ra_khuon"); },
} as const;
const FALLBACK_HINT = tr("he_thong_chua_tu_nhan_ra");
const SECOND_STEP_HINT = tr("dung_o_buoc_hai_neu_tai");

function Recorder({ kind, fields, busy, config }: { kind: "voice" | "webcam"; fields: AuthFields; busy: boolean; config: AuthConfig }) {
  return kind === "voice" ? (
    <AudioRecord key={`a${fields.recordingKey}`} disabled={busy} onRecorded={fields.setAudio} />
  ) : (
    <VideoRecord
      key={`v${fields.recordingKey}`}
      disabled={busy}
      liveness={config}
      onRecorded={(blob, token) => {
        fields.setVideo(blob);
        fields.setLivenessToken(token);
      }}
    />
  );
}

function LoginContent({ tab, config, fields, busy, fail, signIn, passkeySupported }: TabContentProps) {
  switch (tab) {
    case "password":
      return (
        <>
          <UsernameField value={fields.username} onChange={fields.setUsername} />
          <PasswordField value={fields.password} onChange={fields.setPassword} isRegister={false} />
          {config.email_enabled && (
            <p className="text-sm text-right mb-2">
              <Link href="/forgot-password" className="text-line underline">{tr("quen_mat_khau")}</Link>
            </p>
          )}
        </>
      );
    case "voice":
    case "webcam":
      return (
        <>
          {fields.needUsername ? (
            <UsernameField value={fields.username} onChange={fields.setUsername} optionalHint={FALLBACK_HINT} />
          ) : (
            <p className="text-sm text-line mb-2">{AUTO_HINT[tab]}</p>
          )}
          <BiometricWarning kinds={[tab]} />
          <Recorder kind={tab} fields={fields} busy={busy} config={config} />
        </>
      );
    case "totp":
      return (
        <>
          <label htmlFor="auth-totp" className={LABEL}>{tr("ma_xac_thuc_6_chu_so")}</label>
          <TextBox id="auth-totp" value={fields.totpCode} inputMode="numeric" autoComplete="one-time-code" maxLength={TOTP_LENGTH}
                 onChange={(e) => fields.setTotpCode(digitsOnly(e.target.value))} className={INPUT} />
          <p className="text-sm text-line mb-2">{SECOND_STEP_HINT}</p>
        </>
      );
    case "recovery":
      return (
        <>
          <label htmlFor="auth-recovery" className={LABEL}>{tr("ma_khoi_phuc")}</label>
          <TextBox id="auth-recovery" value={fields.recoveryCode} autoComplete="off" autoCapitalize="none" spellCheck={false}
                 onChange={(e) => fields.setRecoveryCode(e.target.value)} className={INPUT} />
          <p className="text-sm text-line mb-2">{SECOND_STEP_HINT} {tr("moi_ma_khoi_phuc_chi_dung")}</p>
        </>
      );
    case "email":
      return <EmailLogin signIn={signIn} busy={busy} />;
    case "phone":
      return <PhoneLogin signIn={signIn} busy={busy} />;
    case "google":
      return (
        <div className="mb-4" aria-busy={busy}>
          {config.google_client_id && (
            <GoogleSignInButton clientId={config.google_client_id} onCredential={(token) => void signIn(() => loginWithGoogle(token))} onError={fail} />
          )}
        </div>
      );
    case "passkey":
      return (
        <>
          <p className="text-sm text-line mb-2">{PASSKEY_LOGIN_HINT}</p>
          {!passkeySupported && <p role="note" className="text-sm text-line mb-2">{PASSKEY_UNSUPPORTED}</p>}
        </>
      );
    case "qr":
      return <QrLogin signIn={signIn} />;
  }
}

const PASSWORD_REGISTER_HINT = tr("dien_mat_khau_va_ten_dang");
const PASSKEY_REGISTER_NOTE = tr("mo_tab_nay_roi_bam_dang");
const DROP_LABEL = tr("khong_dung_cach_nay");

/** Registration has no checkboxes: a method counts as soon as its tab holds something (see AuthPanel). */
function RegisterContent({ tab, config, fields, busy, fail, passkeySupported }: TabContentProps) {
  switch (tab) {
    case "email":
      return (
        <>
          <label htmlFor="register-email" className={LABEL}>{tr("email_tuy_chon_dung_de_khoi")}</label>
          <TextBox id="register-email" type="email" name="email" value={fields.email} autoComplete="email" inputMode="email"
                 onChange={(e) => fields.setEmail(e.target.value)} className={INPUT} />
        </>
      );
    case "password":
      return (
        <>
          <p className="text-sm text-line mb-2">{PASSWORD_REGISTER_HINT}</p>
          <PasswordField value={fields.password} onChange={fields.setPassword} isRegister />
        </>
      );
    case "voice":
    case "webcam": {
      const recorded = tab === "voice" ? fields.audio !== undefined : fields.video !== undefined;
      const drop = () => {
        if (tab === "voice") fields.setAudio(undefined);
        else {
          fields.setVideo(undefined);
          fields.setLivenessToken(undefined);
        }
      };
      return (
        <>
          <BiometricWarning kinds={[tab]} />
          <div className="mb-2"><Recorder kind={tab} fields={fields} busy={busy} config={config} /></div>
          {recorded && (
            <Button type="button" disabled={busy} className="underline text-line text-sm" onClick={() => { drop(); fields.clearRecordings(); }}>
              {DROP_LABEL}
            </Button>
          )}
        </>
      );
    }
    case "google":
      return (
        <div className="mb-3" aria-busy={busy}>
          {fields.googleToken ? (
            <p className="text-sm text-line">
              {tr("da_chon_tai_khoan_google")}{" "}
              <Button type="button" className="underline text-line" onClick={() => fields.setGoogleToken(undefined)}>{tr("chon_lai")}</Button>
            </p>
          ) : (
            config.google_client_id && (
              <>
                <p className="text-sm font-medium mb-1">{tr("chon_tai_khoan_google")}</p>
                <GoogleSignInButton clientId={config.google_client_id} onCredential={fields.setGoogleToken} onError={fail} />
              </>
            )
          )}
        </div>
      );
    case "passkey":
      return (
        <>
          <p className="text-sm text-line mb-2">{PASSKEY_REGISTER_NOTE}</p>
          {!passkeySupported && <p role="note" className="text-sm text-line mb-2">{PASSKEY_UNSUPPORTED}</p>}
        </>
      );
    default:
      return null; // totp, recovery, phone, qr are not offered when registering
  }
}

/** The content of one tab, for the mode being shown. */
export default function AuthTabContent(props: TabContentProps) {
  return props.mode === "login" ? <LoginContent {...props} /> : <RegisterContent {...props} />;
}
