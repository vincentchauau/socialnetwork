"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { setCsrfToken } from "@sn/api";
import Alert from "./Alert";
import BiometricCapture from "./BiometricCapture";
import BiometricWarning from "./BiometricWarning";
import GoogleSignInButton from "./GoogleSignInButton";
import { CARD, INPUT, LABEL, LINK_BUTTON, PRIMARY_BUTTON } from "./ui";
import {
  AuthConfig,
  PASSWORD_MESSAGE,
  Session,
  enrollBiometrics,
  errorText,
  getAuthConfig,
  isPasswordValid,
  loginWithBiometricsOnly,
  loginWithGoogle,
  loginWithPassword,
  registerAccount,
} from "../lib/auth";
import { goTo, postLoginTarget } from "../lib/navigate";

type Mode = "login" | "register";

const NO_CONFIG: AuthConfig = { google_client_id: null, biometrics_enabled: false };

export default function LoginFlow() {
  const [config, setConfig] = useState<AuthConfig>(NO_CONFIG);
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [audio, setAudio] = useState<Blob>();
  const [video, setVideo] = useState<Blob>();
  const [recordingKey, setRecordingKey] = useState(0); // đổi key để các ô ghi âm/quay trở về trạng thái trống
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false); // chặn gửi hai lần ngay cả khi state chưa kịp cập nhật
  const usernameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Chỉ là tính năng tùy chọn: không đọc được cấu hình thì đăng nhập bằng mật khẩu vẫn dùng được.
    getAuthConfig().then(setConfig).catch(() => setConfig(NO_CONFIG));
  }, []);

  const clearRecordings = () => {
    setAudio(undefined);
    setVideo(undefined);
    setRecordingKey((key) => key + 1);
  };

  /** Chạy một yêu cầu đăng nhập; trả true khi đã có phiên và cần rời trang. */
  async function run(action: () => Promise<boolean>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      if (await action()) {
        setPassword("");
        clearRecordings(); // không giữ lại bản ghi sau khi đăng nhập xong
        goTo(postLoginTarget());
        return;
      }
    } catch (caught) {
      setError(errorText(caught));
    }
    busyRef.current = false;
    setBusy(false);
  }

  /** Tài khoản đã tạo xong; ghi âm/quay lúc đăng ký (nếu có) được lưu ngay bằng csrf token của phiên mới. */
  async function enrollAfterRegister(session: Session) {
    if (!config.biometrics_enabled || (!audio && !video)) return;
    setCsrfToken(session.csrf_token);
    try {
      await enrollBiometrics(password, audio, video);
    } catch {
      // Tài khoản đã được tạo và đã đăng nhập: không chặn người dùng, họ có thể thêm lại trong trang Tài khoản.
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (mode === "register" && !isPasswordValid(password)) {
      setError(PASSWORD_MESSAGE);
      return;
    }
    // Đăng nhập chỉ bằng sinh trắc: đã quay xong và để trống mật khẩu (tài khoản phải tự bật tính năng này).
    const biometricOnly = mode === "login" && Boolean(video) && password === "";
    void run(async () => {
      if (mode === "register") {
        await enrollAfterRegister(await registerAccount(username, password));
        return true;
      }
      if (biometricOnly) {
        await loginWithBiometricsOnly(username, audio, video);
        return true;
      }
      await loginWithPassword(username, password); // bản ghi (nếu có) bị bỏ qua, không gửi đi
      return true;
    });
  }

  function switchMode() {
    setMode(mode === "login" ? "register" : "login");
    setError(null);
    clearRecordings(); // bản ghi của chế độ trước không được dùng lại
    usernameRef.current?.focus();
  }

  const title = mode === "login" ? "Đăng nhập" : "Đăng ký";
  const biometricOnly = mode === "login" && Boolean(video) && password === "";
  return (
    <main className={CARD}>
      <h1 className="text-2xl font-bold mb-4">{title}</h1>
      {config.google_client_id && (
        <div className="mb-4" aria-busy={busy}>
          <GoogleSignInButton
            clientId={config.google_client_id}
            onCredential={(token) => void run(async () => {
                await loginWithGoogle(token);
                return true;
              })}
            onError={setError}
          />
        </div>
      )}
      <form onSubmit={submit} aria-label={title}>
        <label htmlFor="username" className={LABEL}>Tên đăng nhập</label>
        <input
          id="username"
          ref={usernameRef}
          name="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className={INPUT}
          required
          minLength={3}
          maxLength={32}
          autoComplete="username"
          aria-describedby="username-hint"
          placeholder="vd: nguyenvan"
        />
        <p id="username-hint" className="text-xs text-gray-600 mb-2">
          3-32 ký tự: chữ thường a-z, số, dấu chấm, gạch dưới, gạch ngang (không dùng @).
        </p>
        <label htmlFor="password" className={LABEL}>Mật khẩu</label>
        <input
          id="password"
          type="password"
          name="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={INPUT}
          required={!biometricOnly}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          placeholder={biometricOnly ? "Bỏ trống để đăng nhập bằng giọng nói + khuôn mặt" : "Ít nhất 8 ký tự"}
        />
        {config.biometrics_enabled && (
          <>
            {mode === "login" ? (
              <p className="text-sm text-gray-600 mb-2">
                Tùy chọn: nhập mật khẩu để đăng nhập bình thường (bản quay sẽ bị bỏ qua). Hoặc để trống mật khẩu và quay
                một đoạn ngắn (nhìn camera, nói vài câu) để đăng nhập bằng khuôn mặt + giọng nói, chỉ khi tài khoản đã bật
                tính năng này.
              </p>
            ) : (
              <p className="text-sm text-gray-600 mb-2">
                Tùy chọn: quay một lần (nhìn camera, nói vài câu) để lưu khuôn mặt + giọng nói cho tài khoản mới. Bạn
                vẫn đăng nhập bằng mật khẩu; đăng nhập không mật khẩu phải được bật riêng trong trang Tài khoản.
              </p>
            )}
            {biometricOnly && <BiometricWarning />}
            <BiometricCapture key={recordingKey} disabled={busy} onVideo={setVideo} onAudio={setAudio} />
          </>
        )}
        <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
          {busy ? "Đang xử lý..." : title}
        </button>
        <button type="button" className={LINK_BUTTON} onClick={switchMode}>
          {mode === "login" ? "Chưa có tài khoản? Đăng ký" : "Đã có tài khoản? Đăng nhập"}
        </button>
        <div className="text-center">
          <Alert text={error} />
        </div>
      </form>
    </main>
  );
}
