import { ApiError, CENTER_API, apiFetch, apiForm, refreshSession } from "@sn/api";

export const MIN_PASSWORD = 8;
export const MAX_PASSWORD = 128;
export const MAX_AUDIO_BYTES = 3 * 1024 * 1024;
export const MAX_VIDEO_BYTES = 15 * 1024 * 1024;

export interface Session {
  id: number;
  username: string;
  role: string;
  csrf_token: string;
}

export interface Me {
  id: number;
  username: string;
  role: string;
  email: string | null;
  has_password: boolean;
  google_linked: boolean;
  has_audio: boolean;
  has_face: boolean;
  biometric_login: boolean;
  passwordless_ready: boolean;
  csrf_token: string;
}

export interface BiometricStatus {
  has_audio: boolean;
  has_face: boolean;
  biometric_login: boolean;
  passwordless_ready: boolean;
}

export interface AuthConfig {
  google_client_id: string | null;
  biometrics_enabled: boolean;
}

export const PASSWORD_MESSAGE = `Mật khẩu cần ít nhất ${MIN_PASSWORD} ký tự`;

export function isPasswordValid(password: string): boolean {
  return password.length >= MIN_PASSWORD && password.length <= MAX_PASSWORD;
}

/** Only same-site relative paths ("/x", never "//host" or "/\host") may be redirected to. */
export function safeNextPath(next: string | null | undefined): string {
  if (!next || next[0] !== "/" || next[1] === "/" || next[1] === "\\") return "/";
  if (/[\\\u0000-\u001f\u007f]/.test(next)) return "/";
  try {
    const parsed = new URL(next, "http://placeholder.invalid");
    return parsed.origin === "http://placeholder.invalid" ? next : "/";
  } catch {
    return "/";
  }
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) return "Thử quá nhiều lần, hãy thử lại sau";
  return error instanceof Error ? error.message : "Có lỗi xảy ra, hãy thử lại";
}

export function assertBlobSizes(audio?: Blob, video?: Blob): void {
  if (audio && audio.size > MAX_AUDIO_BYTES) throw new Error("Bản ghi giọng nói quá lớn (tối đa 3 MB)");
  if (video && video.size > MAX_VIDEO_BYTES) throw new Error("Bản quay phim quá lớn (tối đa 15 MB)");
}

function biometricForm(fields: Record<string, string | undefined>, audio?: Blob, video?: Blob): FormData {
  assertBlobSizes(audio, video);
  const form = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    if (value !== undefined) form.append(key, value);
  }
  if (audio) form.append("audio", audio, "audio.webm");
  if (video) form.append("video", video, "video.webm");
  return form;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const getAuthConfig = () => apiFetch<AuthConfig>(`${CENTER_API}/auth/config`);

export const loginWithPassword = (username: string, password: string) =>
  apiFetch<Session>(`${CENTER_API}/auth/login`, json({ username, password }));

export const registerAccount = (username: string, password: string) =>
  apiFetch<Session>(`${CENTER_API}/auth/register`, json({ username, password }));

export const loginWithGoogle = (idToken: string) =>
  apiFetch<Session>(`${CENTER_API}/auth/google`, json({ id_token: idToken }));

/** Passwordless sign-in (opt-in per account): needs a username and a recorded clip. */
export const loginWithBiometricsOnly = (username: string, audio?: Blob, video?: Blob) =>
  apiForm<Session>(`${CENTER_API}/auth/login/biometric-only`, biometricForm({ username }, audio, video));

export const fetchMe = () => apiFetch<Me>(`${CENTER_API}/auth/me`);

/** The account details, or null when signed out. A 401 first tries the refresh cookie once. */
export async function loadMe(): Promise<Me | null> {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      return await fetchMe();
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
      if (attempt === 1 || !(await refreshSession())) return null;
    }
  }
  return null;
}

export const logout = () => apiFetch<void>(`${CENTER_API}/auth/logout`, { method: "POST" });

export const changePassword = (newPassword: string, currentPassword?: string) =>
  apiFetch<Session>(
    `${CENTER_API}/auth/me/password`,
    json({ new_password: newPassword, current_password: currentPassword }),
  );

export const linkGoogle = (idToken: string, password?: string) =>
  apiFetch<unknown>(`${CENTER_API}/auth/me/google`, json({ id_token: idToken, password }));

export const deleteAccount = (password?: string) =>
  apiFetch<void>(`${CENTER_API}/auth/me`, { method: "DELETE", body: JSON.stringify({ password }) });

export const enrollBiometrics = (password: string | undefined, audio?: Blob, video?: Blob) =>
  apiForm<BiometricStatus>(`${CENTER_API}/auth/me/biometrics`, biometricForm({ password }, audio, video));

export const setBiometricLogin = (enabled: boolean, password?: string) =>
  apiForm<unknown>(
    `${CENTER_API}/auth/me/biometric-login`,
    biometricForm({ enabled: String(enabled), password }),
    { method: "PUT" },
  );

export const deleteBiometrics = (password?: string) =>
  apiForm<unknown>(`${CENTER_API}/auth/me/biometrics`, biometricForm({ password }), { method: "DELETE" });
