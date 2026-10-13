"use client";

import { FormEvent, useState } from "react";

import { ApiError } from "@sn/api";

import Alert from "./Alert";
import AudioRecord from "./AudioRecord";
import EmailLogin from "./EmailLogin";
import PhoneLogin from "./PhoneLogin";
import QrLogin from "./QrLogin";
import BiometricWarning from "./BiometricWarning";
import GoogleSignInButton from "./GoogleSignInButton";
import MethodTabs, { Method } from "./MethodTabs";
import PasswordField from "./PasswordField";
import UsernameField from "./UsernameField";
import VideoRecord from "./VideoRecord";
import { PRIMARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { usePasskeySupport } from "../hooks/usePasskeySupport";
import {
  AuthConfig,
  USERNAME_NEEDED,
  LoginResult,
  MfaChallenge,
  loginWithGoogle,
  loginWithPasskey,
  loginWithPassword,
  loginWithVoice,
  loginWithWebcam,
  passkeyLoginOptions,
} from "../lib/auth";
import { goTo, postLoginTarget } from "../lib/navigate";
import { PASSKEY_UNSUPPORTED, getPasskeyCredential } from "../lib/passkey";

interface Props {
  config: AuthConfig;
  onMfa: (challenge: MfaChallenge) => void;
}

export function availableMethods(config: AuthConfig): Method[] {
  const methods: Method[] = ["password"];
  if (config.google_client_id) methods.push("google");
  if (config.biometrics_enabled) methods.push("voice", "webcam");
  methods.push("passkey");
  return methods;
}

/**
 * Thứ tự tab: các cách cùng chuỗi thông điệp nằm cạnh nhau (xem SPEC.md).
 *   A → S                 Mật khẩu, Giọng nói, Webcam
 *   A → S → B ⇢ A → S     Email, Điện thoại (mã gửi qua kênh ngoài)
 *   A → G → A → S         Google
 *   A → S → A → B → A → S Passkey
 *   A → S → A ⇢ B → S → A Mã QR
 */
export function signInMethods(config: AuthConfig): Method[] {
  const methods: Method[] = ["password"];
  if (config.biometrics_enabled) methods.push("voice", "webcam");
  if (config.email_enabled) methods.push("email");
  if (config.phone_enabled) methods.push("phone");
  if (config.google_client_id) methods.push("google");
  methods.push("passkey", "qr");
  return methods;
}

const PASSKEY_HINT = "Dùng vân tay, Face ID, Windows Hello hoặc khóa bảo mật của thiết bị. Không cần nhập tên đăng nhập.";

const AUTO_HINT = {
  voice: "Hệ thống tự nhận ra giọng nói của bạn.",
  webcam: "Hệ thống tự nhận ra khuôn mặt của bạn.",
} as const;

const FALLBACK_HINT = "Hệ thống chưa tự nhận ra bạn được, hãy nhập tên đăng nhập rồi gửi lại.";

/** Đăng nhập bằng MỘT cách: mật khẩu, Google, giọng nói hoặc webcam. */
export default function SignInForm({ config, onMfa }: Props) {
  const [method, setMethod] = useState<Method>("password");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [audio, setAudio] = useState<Blob>();
  const [video, setVideo] = useState<Blob>();
  const [livenessToken, setLivenessToken] = useState<string>();
  const [needUsername, setNeedUsername] = useState(false); // chỉ hiện khi máy chủ yêu cầu (hệ thống rất lớn)
  const [recordingKey, setRecordingKey] = useState(0); // đổi key để ô ghi âm/quay trở về trạng thái trống
  const { busy, error, run, fail } = useAction();
  const passkeySupported = usePasskeySupport();

  const clearRecordings = () => {
    setAudio(undefined);
    setVideo(undefined);
    setLivenessToken(undefined);
    setRecordingKey((key) => key + 1);
  };

  function pick(next: Method) {
    if (next === method) return;
    setMethod(next);
    setPassword("");
    setNeedUsername(false);
    clearRecordings(); // bản ghi của cách trước không được dùng lại
    fail("");
  }

  /** Có phiên thì về trang đích, cần xác minh thêm thì chuyển sang bước đó. */
  async function signIn(action: () => Promise<LoginResult | undefined>) {
    let challenge: MfaChallenge | null = null;
    const ok = await run(async () => {
      const result = await action();
      if (result && result.kind === "mfa") challenge = { mfaToken: result.mfaToken, factors: result.factors };
    });
    setPassword("");
    clearRecordings();
    if (!ok) return;
    if (challenge) onMfa(challenge);
    else goTo(postLoginTarget());
  }

  /** 422 "Enter your username": giữ nguyên tab và hiện ô tên đăng nhập. */
  async function withUsernameFallback<T>(call: () => Promise<T>): Promise<T> {
    try {
      return await call();
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 422 && caught.message === USERNAME_NEEDED) setNeedUsername(true);
      throw caught;
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (method === "voice") {
      if (!audio) return fail("Hãy ghi giọng nói trước khi đăng nhập");
      return void signIn(() => withUsernameFallback(() => loginWithVoice(audio, needUsername ? username : undefined)));
    }
    if (method === "webcam") {
      if (!video) return fail("Hãy quay khuôn mặt trước khi đăng nhập");
      return void signIn(() => withUsernameFallback(() => loginWithWebcam(video, needUsername ? username : undefined, livenessToken)));
    }
    if (method === "passkey") {
      if (!passkeySupported) return fail(PASSKEY_UNSUPPORTED);
      return void signIn(async () => {
        const { options, challenge_token } = await passkeyLoginOptions();
        const credential = await getPasskeyCredential(options);
        return { kind: "session", session: await loginWithPasskey(credential, challenge_token) };
      });
    }
    void signIn(() => loginWithPassword(username, password));
  }

  return (
    <>
      <MethodTabs methods={signInMethods(config)} value={method} disabled={busy} onChange={pick} />
      <div role="tabpanel" aria-labelledby={`tab-${method}`}>
        {method === "google" && config.google_client_id ? (
          <div className="mb-4" aria-busy={busy}>
            <GoogleSignInButton
              clientId={config.google_client_id}
              onCredential={(token) => void signIn(() => loginWithGoogle(token))}
              onError={fail}
            />
          </div>
        ) : method === "email" && config.email_enabled ? (
          <EmailLogin signIn={signIn} busy={busy} />
        ) : method === "phone" && config.phone_enabled ? (
          <PhoneLogin signIn={signIn} busy={busy} />
        ) : method === "qr" ? (
          <QrLogin signIn={signIn} />
        ) : (
          <form onSubmit={submit} aria-label="Đăng nhập">
            {(method === "password" || needUsername) && (
              <UsernameField value={username} onChange={setUsername} optionalHint={needUsername ? FALLBACK_HINT : undefined} />
            )}
            {(method === "voice" || method === "webcam") && !needUsername && (
              <p className="text-sm text-gray-600 mb-2">{AUTO_HINT[method]}</p>
            )}
            {method === "passkey" && (
              <>
                <p className="text-sm text-gray-600 mb-2">{PASSKEY_HINT}</p>
                {!passkeySupported && <p role="note" className="text-sm text-red-600 mb-2">{PASSKEY_UNSUPPORTED}</p>}
              </>
            )}
            {method === "password" && <PasswordField value={password} onChange={setPassword} isRegister={false} />}
            {(method === "voice" || method === "webcam") && <BiometricWarning kinds={[method]} />}
            {method === "voice" && <AudioRecord key={recordingKey} disabled={busy} onRecorded={setAudio} />}
            {method === "webcam" && (
              <VideoRecord
                key={recordingKey}
                disabled={busy}
                liveness={config}
                onRecorded={(blob, token) => {
                  setVideo(blob);
                  setLivenessToken(token);
                }}
              />
            )}
            {method === "password" && config.email_enabled && (
              <p className="text-sm text-right mb-2">
                <a href="/forgot-password" className="text-blue-700 underline">Quên mật khẩu?</a>
              </p>
            )}
            <button type="submit" disabled={busy || (method === "passkey" && !passkeySupported)} className={`${PRIMARY_BUTTON} mt-2`}>
              {busy ? "Đang xử lý..." : method === "passkey" ? "Đăng nhập bằng Passkey" : "Đăng nhập"}
            </button>
          </form>
        )}
      </div>
      <div className="text-center">
        <Alert text={error} />
      </div>
    </>
  );
}
