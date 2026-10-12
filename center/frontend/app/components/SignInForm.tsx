"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
import AudioRecord from "./AudioRecord";
import BiometricWarning from "./BiometricWarning";
import GoogleSignInButton from "./GoogleSignInButton";
import MethodTabs, { Method } from "./MethodTabs";
import PasswordField from "./PasswordField";
import UsernameField from "./UsernameField";
import VideoRecord from "./VideoRecord";
import { PRIMARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import {
  AuthConfig,
  LoginResult,
  loginWithGoogle,
  loginWithPassword,
  loginWithVoice,
  loginWithWebcam,
} from "../lib/auth";
import { goTo, postLoginTarget } from "../lib/navigate";

interface Props {
  config: AuthConfig;
  onMfa: (mfaToken: string) => void;
}

export function availableMethods(config: AuthConfig): Method[] {
  const methods: Method[] = ["password"];
  if (config.google_client_id) methods.push("google");
  if (config.biometrics_enabled) methods.push("voice", "webcam");
  return methods;
}

const WEBCAM_HINT =
  "Chỉ cần khuôn mặt, không cần giọng nói. Để trống: hệ thống tự nhận ra khuôn mặt của bạn. Nhập tên nếu muốn đối chiếu đúng tài khoản.";

/** Đăng nhập bằng MỘT cách: mật khẩu, Google, giọng nói hoặc webcam. */
export default function SignInForm({ config, onMfa }: Props) {
  const [method, setMethod] = useState<Method>("password");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [audio, setAudio] = useState<Blob>();
  const [video, setVideo] = useState<Blob>();
  const [recordingKey, setRecordingKey] = useState(0); // đổi key để ô ghi âm/quay trở về trạng thái trống
  const { busy, error, run, fail } = useAction();

  const clearRecordings = () => {
    setAudio(undefined);
    setVideo(undefined);
    setRecordingKey((key) => key + 1);
  };

  function pick(next: Method) {
    if (next === method) return;
    setMethod(next);
    setPassword("");
    clearRecordings(); // bản ghi của cách trước không được dùng lại
    fail("");
  }

  /** Có phiên thì về trang đích, cần xác minh thêm thì chuyển sang bước đó. */
  async function signIn(action: () => Promise<LoginResult | undefined>) {
    let mfaToken: string | null = null;
    const ok = await run(async () => {
      const result = await action();
      if (result && result.kind === "mfa") mfaToken = result.mfaToken;
    });
    setPassword("");
    clearRecordings();
    if (!ok) return;
    if (mfaToken) onMfa(mfaToken);
    else goTo(postLoginTarget());
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (method === "voice") {
      if (!audio) return fail("Hãy ghi giọng nói trước khi đăng nhập");
      return void signIn(async () => void (await loginWithVoice(username, audio)));
    }
    if (method === "webcam") {
      if (!video) return fail("Hãy quay khuôn mặt trước khi đăng nhập");
      return void signIn(async () => void (await loginWithWebcam(video, username)));
    }
    void signIn(() => loginWithPassword(username, password));
  }

  return (
    <>
      <MethodTabs methods={availableMethods(config)} value={method} disabled={busy} onChange={pick} />
      <div role="tabpanel" aria-labelledby={`tab-${method}`}>
        {method === "google" && config.google_client_id ? (
          <div className="mb-4" aria-busy={busy}>
            <GoogleSignInButton
              clientId={config.google_client_id}
              onCredential={(token) => void signIn(() => loginWithGoogle(token))}
              onError={fail}
            />
          </div>
        ) : (
          <form onSubmit={submit} aria-label="Đăng nhập">
            <UsernameField
              value={username}
              onChange={setUsername}
              required={method !== "webcam"}
              optionalHint={WEBCAM_HINT}
            />
            {method === "password" && <PasswordField value={password} onChange={setPassword} isRegister={false} />}
            {(method === "voice" || method === "webcam") && <BiometricWarning kinds={[method]} />}
            {method === "voice" && <AudioRecord key={recordingKey} disabled={busy} onRecorded={setAudio} />}
            {method === "webcam" && <VideoRecord key={recordingKey} disabled={busy} onRecorded={setVideo} />}
            <button type="submit" disabled={busy} className={`${PRIMARY_BUTTON} mt-2`}>
              {busy ? "Đang xử lý..." : "Đăng nhập"}
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
