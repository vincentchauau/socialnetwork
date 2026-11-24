"use client";

import { ApiError } from "@sn/api";
import { type KeyboardEvent, type ReactNode, useState } from "react";

import AccountMode from "./AccountMode";
import Alert from "@sn/elements/Alert";
import AuthTabContent, { type SignIn } from "./AuthTabContent";
import { TOTP_LENGTH, codeError, normaliseRecoveryCode } from "./TotpLoginForm";
import UsernameField from "./UsernameField";
import ModeSwitch from "./ModeSwitch";
import { PRIMARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { useAuthFields } from "../hooks/useAuthFields";
import { usePasskeySupport } from "../hooks/usePasskeySupport";
import {
  AuthConfig,
  EMAIL_INVALID,
  MfaChallenge,
  MfaFactor,
  PASSWORD_MESSAGE,
  USERNAME_NEEDED,
  isEmailValid,
  isPasswordValid,
  loginWithPassword,
  loginWithPasskey,
  loginWithTotp,
  loginWithVoice,
  loginWithWebcam,
  passkeyLoginOptions,
  passkeyRegisterOptions,
  registerCombined,
  rememberNewUsername,
  rememberVerificationEmail,
  type CombinedRegistration,
} from "../lib/auth";
import { type AuthMode, type EntryMode, SELF_ACTING_TABS, type AuthTab, TAB_LABEL, authTree, availableTabs, tabKey, tabOf } from "../lib/authTabs";
import { goTo, postLoginTarget } from "../lib/navigate";
import { PASSKEY_UNSUPPORTED, createPasskeyCredential, getPasskeyCredential } from "../lib/passkey";
import Button from "@sn/elements/Button";
import { TabPanel } from "@sn/compounds/SplitPanel";
import ProfileFields from "./ProfileFields";
import { ProfileProblem, draftOf, patchOf, rememberProfileUnsaved, saveProfile } from "../lib/profile";
import { tr } from "../i18n";

const OPTIONAL_HINT = tr("khong_bat_buoc_neu_chi_dung");


interface Props {
  config: AuthConfig;
  onMfa: (challenge: MfaChallenge) => void;
  /** Whether a session exists: only then is "Cập nhật" offered. */
  signedIn?: boolean;
  /** The mode to open in: "account" for a visitor who is signed in. */
  initialMode?: AuthMode;
}

function AuthForm({ mode, config, onMfa }: Props & { mode: EntryMode }) {
  const fields = useAuthFields();
  const [active, setActive] = useState<AuthTab>("password");
  const { busy, error, run, fail } = useAction();
  const passkeySupported = usePasskeySupport();
  const [profile, setProfile] = useState(() => draftOf(null));
  const tabs = availableTabs(mode, config);
  const current = tabs.includes(active) ? active : "password";

  /**
   * Opening another tab drops what was recorded for the previous one (a clip is never reused for another method) and the
   * username fallback. Sign-in only: registration keeps every tab's recording, and the password and the TOTP or recovery
   * code stay too, because the tabs are used together.
   */
  function openTab(key: string) {
    const next = tabOf(key);
    if (next === current) return;
    setActive(next);
    fail("");
    if (mode === "login") {
      fields.clearRecordings();
      fields.setNeedUsername(false);
    }
  }

  /**
   * Registration has no checkboxes: a method counts once its tab holds something, in tab order. Passkey has nothing to
   * fill, so it counts while its tab is the open one when the button is pressed.
   */
  const used: AuthTab[] = mode === "register"
    ? [
        ...(fields.password ? (["password"] as const) : []),
        ...(fields.video ? (["webcam"] as const) : []),
        ...(fields.audio ? (["voice"] as const) : []),
        ...(fields.googleToken ? (["google"] as const) : []),
        ...(current === "passkey" ? (["passkey"] as const) : []),
      ]
    : [];

  /** A code filled in the TOTP or recovery tab is sent at step two, so an account with 2FA signs in in one go. */
  function secondStepProof(factors: MfaFactor[]) {
    if (!factors.includes("totp")) return undefined;
    const recovery = normaliseRecoveryCode(fields.recoveryCode);
    if (recovery) return { recoveryCode: recovery };
    return fields.totpCode.length === TOTP_LENGTH ? { code: fields.totpCode } : undefined;
  }

  /** A session goes to the target page; a challenge nobody answered goes to the step-two screen. */
  const signIn: SignIn = async (action) => {
    let challenge: MfaChallenge | null = null;
    const ok = await run(async () => {
      const result = await action();
      if (result?.kind !== "mfa") return;
      const proof = secondStepProof(result.factors);
      if (!proof) {
        challenge = { mfaToken: result.mfaToken, factors: result.factors };
        return;
      }
      try {
        await loginWithTotp(result.mfaToken, proof);
      } catch (caught) {
        throw codeError(caught);
      }
    });
    fields.clearSecrets();
    if (!ok) return;
    if (challenge) onMfa(challenge);
    else goTo(postLoginTarget());
  };

  /** 422 "Enter your username": stay on the tab and show the username field. */
  async function withUsernameFallback<T>(call: () => Promise<T>): Promise<T> {
    try {
      return await call();
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 422 && caught.message === USERNAME_NEEDED) fields.setNeedUsername(true);
      throw caught;
    }
  }

  function submitLogin() {
    const name = fields.needUsername ? fields.username : undefined;
    if (current === "voice") {
      if (!fields.audio) return fail(tr("hay_ghi_giong_noi_truoc_khi"));
      const audio = fields.audio;
      return void signIn(() => withUsernameFallback(() => loginWithVoice(audio, name)));
    }
    if (current === "webcam") {
      if (!fields.video) return fail(tr("hay_quay_khuon_mat_truoc_khi"));
      const video = fields.video;
      return void signIn(() => withUsernameFallback(() => loginWithWebcam(video, name, fields.livenessToken)));
    }
    if (current === "passkey") {
      if (!passkeySupported) return fail(PASSKEY_UNSUPPORTED);
      return void signIn(async () => {
        const { options, challenge_token } = await passkeyLoginOptions();
        const credential = await getPasskeyCredential(options);
        return { kind: "session", session: await loginWithPasskey(credential, challenge_token) };
      });
    }
    // Password, TOTP and recovery tabs: the primary credential is the password (the codes are the second step).
    if (!fields.username.trim() || !fields.password) {
      return fail(current === "password" ? tr("hay_nhap_ten_dang_nhap_va") : tr("hay_nhap_ten_dang_nhap_va_2"));
    }
    void signIn(() => loginWithPassword(fields.username, fields.password));
  }

  /** Máy chủ cấp thử thách, thiết bị tạo khóa; kết quả đi kèm yêu cầu đăng ký. */
  async function createPasskey(): Promise<Pick<CombinedRegistration, "passkeyCredential" | "passkeyChallengeToken">> {
    const { options, challenge_token } = await passkeyRegisterOptions(fields.username);
    return { passkeyCredential: await createPasskeyCredential(options), passkeyChallengeToken: challenge_token };
  }

  async function submitRegister() {
    if (used.length === 0) return fail(tr("hay_dien_it_nhat_mot_cach"));
    if (used.includes("password") && !isPasswordValid(fields.password)) return fail(PASSWORD_MESSAGE);
    if (used.includes("password") && !fields.username.trim()) return fail(tr("hay_nhap_ten_dang_nhap"));
    if (used.includes("passkey") && !passkeySupported) return fail(PASSKEY_UNSUPPORTED);
    const cleanEmail = fields.email.trim();
    if (cleanEmail && !isEmailValid(cleanEmail)) return fail(EMAIL_INVALID);
    let profilePatch: Record<string, unknown>;
    try {
      profilePatch = patchOf(profile, draftOf(null)); // checked first: a bad row is told before anything is created
    } catch (caught) {
      return fail(caught instanceof ProfileProblem ? caught.message : tr("co_loi_xay_ra_hay_thu"));
    }
    let created: string | undefined;
    const ok = await run(async () => {
      const passkey = used.includes("passkey") ? await createPasskey() : {};
      const session = await registerCombined({
        ...passkey,
        username: fields.username,
        email: cleanEmail || undefined,
        password: used.includes("password") ? fields.password : undefined,
        googleIdToken: fields.googleToken,
        voiceAudio: fields.audio,
        webcamVideo: fields.video,
        livenessToken: used.includes("webcam") ? fields.livenessToken : undefined,
      });
      created = session.username;
      if (Object.keys(profilePatch).length > 0) {
        // The account exists now: a profile that cannot be saved is told on the next screen, not an error here.
        try {
          await saveProfile(profilePatch);
        } catch {
          rememberProfileUnsaved();
        }
      }
    });
    fields.clearRecordings(); // a used (or failed) recording is never kept
    if (!ok) return;
    fields.setPassword("");
    if (!fields.username.trim() && created) rememberNewUsername(created);
    if (cleanEmail) rememberVerificationEmail(cleanEmail);
    goTo(postLoginTarget());
  }

  const submit = () => (mode === "login" ? submitLogin() : void submitRegister());

  function onEnter(event: KeyboardEvent<HTMLElement>) {
    const target = event.target as HTMLElement;
    if (event.key !== "Enter" || target.tagName !== "INPUT" || (target as HTMLInputElement).type === "checkbox") return;
    if (mode === "login" && SELF_ACTING_TABS.includes(current)) return; // the tab's own form handles Enter
    event.preventDefault();
    submit();
  }

  const panels: Record<string, ReactNode> = {};
  for (const tab of tabs) {
    panels[tabKey(tab)] = (
      <AuthTabContent tab={tab} mode={mode} config={config} fields={fields} busy={busy} fail={fail} signIn={signIn}
                      passkeySupported={passkeySupported} />
    );
  }

  const selfActing = mode === "login" && SELF_ACTING_TABS.includes(current);
  const label = mode === "register" ? tr("dang_ky") : current === "passkey" ? tr("dang_nhap_bang_passkey") : tr("dang_nhap");
  return (
    <div onKeyDown={onEnter}>
      {mode === "register" && (
        <UsernameField value={fields.username} onChange={fields.setUsername} required={used.includes("password")} optionalHint={OPTIONAL_HINT} />
      )}
      <TabPanel
        aria-label={mode === "login" ? tr("cach_dang_nhap") : tr("cach_dang_ky")}
        data={authTree(mode, config)}
        panels={panels}
        keepMounted={mode === "register"}
        onChange={openTab}
      />
      {mode === "register" && (
        <details className="border rounded p-2 mt-2">
          <summary className="font-medium cursor-pointer">{tr("pf_ho_so_khong_bat_buoc")}</summary>
          <div className="mt-2">
            <ProfileFields draft={profile} onChange={setProfile} />
          </div>
        </details>
      )}
      {mode === "register" && (
        <p className="text-sm text-line text-center mt-2">
          {used.length > 0 ? tr("se_dang_ky_bang_p0", { p0: used.map((tab) => TAB_LABEL[tab]).join(", ") }) : tr("dien_mot_tab_mat_khau_giong")}
        </p>
      )}
      {selfActing ? (
        <p className="text-sm text-line text-center mt-2">{tr("hoan_tat_bang_nut_ngay_trong")}</p>
      ) : (
        <Button type="button" disabled={busy || (mode === "login" && current === "passkey" && !passkeySupported)} onClick={submit}
                className={`${PRIMARY_BUTTON} mt-2`}>
          {busy ? tr("dang_xu_ly") : label}
        </Button>
      )}
      <div className="text-center">
        <Alert className="mt-2">{error}</Alert>
      </div>
    </div>
  );
}

/** Đăng nhập, Đăng ký và Đổi tài khoản trên một trang: một TabPanel, mỗi tab một cách xác thực, nút ở dưới. */
export default function AuthPanel({ config, onMfa, signedIn = false, initialMode = "login" }: Props) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
  return (
    <main className="w-full max-w-none mt-6 text-line">
      <ModeSwitch current={mode} onPick={setMode} signedIn={signedIn} />
      {/* key: đổi chế độ thì dựng lại, xóa mọi dữ liệu và bản ghi cũ */}
      {mode === "account" ? <AccountMode config={config} /> : <AuthForm key={mode} mode={mode} config={config} onMfa={onMfa} />}
    </main>
  );
}
