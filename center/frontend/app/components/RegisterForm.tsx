"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
import AudioRecord from "./AudioRecord";
import BiometricWarning, { WarningKind } from "./BiometricWarning";
import GoogleSignInButton from "./GoogleSignInButton";
import { METHOD_LABEL, Method } from "./MethodTabs";
import PasswordField from "./PasswordField";
import { availableMethods } from "./SignInForm";
import UsernameField from "./UsernameField";
import VideoRecord from "./VideoRecord";
import { INPUT, LABEL, PRIMARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { usePasskeySupport } from "../hooks/usePasskeySupport";
import {
  AuthConfig,
  CombinedRegistration,
  EMAIL_INVALID,
  PASSWORD_MESSAGE,
  isEmailValid,
  isPasswordValid,
  passkeyRegisterOptions,
  registerCombined,
  rememberNewUsername,
  rememberVerificationEmail,
} from "../lib/auth";
import { goTo, postLoginTarget } from "../lib/navigate";
import { PASSKEY_UNSUPPORTED, createPasskeyCredential } from "../lib/passkey";

type Chosen = Record<Method, boolean>;

const DEFAULT_CHOSEN: Chosen = {
  password: true,
  google: false,
  voice: false,
  webcam: false,
  passkey: false,
  email: false,
  phone: false,
  qr: false,
};

const OPTIONAL_HINT = "Không bắt buộc nếu chỉ dùng Google, Giọng nói, Webcam hoặc Passkey: hệ thống sẽ tự tạo tên (ví dụ user-7f3a2c).";

const warningKinds = (chosen: Chosen): WarningKind[] => [
  ...(chosen.voice ? (["voice"] as const) : []),
  ...(chosen.webcam ? (["webcam"] as const) : []),
];

/** Tên đăng nhập chỉ bắt buộc khi có mật khẩu; Google, giọng nói, webcam tự nhận ra tài khoản. */
const isUsernameRequired = (chosen: Chosen) => chosen.password;

/** Đăng ký bằng một hoặc nhiều cách cùng lúc; cách còn thiếu bổ sung sau ở trang Tài khoản. */
export default function RegisterForm({ config }: { config: AuthConfig }) {
  const [chosen, setChosen] = useState<Chosen>(DEFAULT_CHOSEN);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [googleToken, setGoogleToken] = useState<string>();
  const [audio, setAudio] = useState<Blob>();
  const [video, setVideo] = useState<Blob>();
  const [livenessToken, setLivenessToken] = useState<string>();
  const [recordingKey, setRecordingKey] = useState(0);
  const { busy, error, run, fail } = useAction();
  const passkeySupported = usePasskeySupport();

  /** Máy chủ cấp thử thách, thiết bị tạo khóa; kết quả đi kèm yêu cầu đăng ký. */
  async function createPasskey(): Promise<Pick<CombinedRegistration, "passkeyCredential" | "passkeyChallengeToken">> {
    const { options, challenge_token } = await passkeyRegisterOptions(username);
    return { passkeyCredential: await createPasskeyCredential(options), passkeyChallengeToken: challenge_token };
  }

  function toggle(method: Method, checked: boolean) {
    setChosen({ ...chosen, [method]: checked });
    if (checked) return;
    // Bỏ chọn một cách thì xóa dữ liệu của nó.
    if (method === "password") setPassword("");
    if (method === "google") setGoogleToken(undefined);
    if (method === "voice") setAudio(undefined);
    if (method === "webcam") {
      setVideo(undefined);
      setLivenessToken(undefined);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!Object.values(chosen).some(Boolean)) return fail("Hãy chọn ít nhất một cách đăng ký");
    if (chosen.password && !isPasswordValid(password)) return fail(PASSWORD_MESSAGE);
    if (chosen.google && !googleToken) return fail("Hãy chọn tài khoản Google trước khi đăng ký");
    if (chosen.voice && !audio) return fail("Hãy ghi giọng nói trước khi đăng ký");
    if (chosen.webcam && !video) return fail("Hãy quay khuôn mặt trước khi đăng ký");
    if (isUsernameRequired(chosen) && !username.trim()) return fail("Hãy nhập tên đăng nhập");
    if (chosen.passkey && !passkeySupported) return fail(PASSKEY_UNSUPPORTED);
    const cleanEmail = email.trim();
    if (cleanEmail && !isEmailValid(cleanEmail)) return fail(EMAIL_INVALID);
    let created: string | undefined;
    const ok = await run(async () => {
      const passkey = chosen.passkey ? await createPasskey() : {};
      const session = await registerCombined({
        ...passkey,
        username,
        email: cleanEmail || undefined,
        password: chosen.password ? password : undefined,
        googleIdToken: chosen.google ? googleToken : undefined,
        voiceAudio: chosen.voice ? audio : undefined,
        webcamVideo: chosen.webcam ? video : undefined,
        livenessToken: chosen.webcam ? livenessToken : undefined,
      });
      created = session.username;
    });
    // Bản ghi đã dùng (hoặc lỗi) không được giữ lại.
    setAudio(undefined);
    setVideo(undefined);
    setLivenessToken(undefined);
    setRecordingKey((key) => key + 1);
    if (!ok) return;
    setPassword("");
    if (!username.trim() && created) rememberNewUsername(created);
    if (cleanEmail) rememberVerificationEmail(cleanEmail);
    goTo(postLoginTarget());
  }

  return (
    <form onSubmit={submit} aria-label="Đăng ký">
      <UsernameField value={username} onChange={setUsername} required={isUsernameRequired(chosen)} optionalHint={OPTIONAL_HINT} />
      <fieldset className="mb-3 border rounded p-2" disabled={busy}>
        <legend className="text-sm font-medium px-1">Chọn các cách đăng ký trước, bổ sung cách còn thiếu sau</legend>
        {availableMethods(config).map((method) => {
          const unavailable = method === "passkey" && !passkeySupported;
          return (
            <label key={method} className="flex items-center gap-2 py-1">
              <input type="checkbox" checked={chosen[method]} disabled={unavailable}
                     onChange={(e) => toggle(method, e.target.checked)} />
              {METHOD_LABEL[method]}
              {unavailable && <span className="text-xs text-gray-600">({PASSKEY_UNSUPPORTED})</span>}
            </label>
          );
        })}
      </fieldset>
      {config.email_enabled && (
        <>
          <label htmlFor="register-email" className={LABEL}>Email (tùy chọn, dùng để khôi phục tài khoản)</label>
          <input id="register-email" type="email" name="email" value={email} autoComplete="email" inputMode="email"
                 onChange={(e) => setEmail(e.target.value)} className={INPUT} />
        </>
      )}
      {chosen.password && <PasswordField value={password} onChange={setPassword} isRegister />}
      {chosen.google && config.google_client_id && (
        <div className="mb-3" aria-busy={busy}>
          {googleToken ? (
            <p className="text-sm text-green-700">
              Đã chọn tài khoản Google{" "}
              <button type="button" className="underline text-blue-700" onClick={() => setGoogleToken(undefined)}>
                Chọn lại
              </button>
            </p>
          ) : (
            <>
              <p className="text-sm font-medium mb-1">Chọn tài khoản Google</p>
              <GoogleSignInButton clientId={config.google_client_id} onCredential={setGoogleToken} onError={fail} />
            </>
          )}
        </div>
      )}
      {chosen.passkey && (
        <p className="text-sm text-gray-600 mb-2">
          Khi bấm Đăng ký, thiết bị sẽ hỏi vân tay, Face ID, Windows Hello hoặc khóa bảo mật để tạo Passkey.
        </p>
      )}
      {(chosen.voice || chosen.webcam) && <BiometricWarning kinds={warningKinds(chosen)} />}
      {chosen.voice && (
        <div className="mb-2">
          <AudioRecord key={`a${recordingKey}`} disabled={busy} onRecorded={setAudio} />
        </div>
      )}
      {chosen.webcam && (
        <div className="mb-2">
          <VideoRecord
            key={`v${recordingKey}`}
            disabled={busy}
            liveness={config}
            onRecorded={(blob, token) => {
              setVideo(blob);
              setLivenessToken(token);
            }}
          />
        </div>
      )}
      <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
        {busy ? "Đang xử lý..." : "Đăng ký"}
      </button>
      <div className="text-center">
        <Alert text={error} />
      </div>
    </form>
  );
}
