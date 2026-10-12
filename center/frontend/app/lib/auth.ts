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
  voice_login: boolean;
  webcam_login: boolean;
  has_audio: boolean;
  has_face: boolean;
  require_biometric_2fa: boolean;
  csrf_token: string;
}

export interface MethodsStatus {
  has_password: boolean;
  google_linked: boolean;
  voice_login: boolean;
  webcam_login: boolean;
  has_audio: boolean;
  has_face: boolean;
  require_biometric_2fa: boolean;
}

export interface AuthConfig {
  google_client_id: string | null;
  biometrics_enabled: boolean;
}

export type LoginResult = { kind: "session"; session: Session } | { kind: "mfa"; mfaToken: string };

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

export const USERNAME_NEEDED = "Enter your username";
const VOICE_TAKEN = "This voice is already registered";
const VOICE_TAKEN_HELP = "Giọng nói này đã được đăng ký cho một tài khoản khác, hãy đăng nhập hoặc dùng giọng khác.";

export function errorText(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) return "Thử quá nhiều lần, hãy thử lại sau";
  if (error instanceof Error && error.message === VOICE_TAKEN) return `${VOICE_TAKEN}. ${VOICE_TAKEN_HELP}`;
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

type SessionOrMfa = Session | { mfa_required: true; mfa_token: string };

function toLoginResult(body: SessionOrMfa): LoginResult {
  if ("mfa_required" in body && body.mfa_required) return { kind: "mfa", mfaToken: body.mfa_token };
  return { kind: "session", session: body as Session };
}

export async function loginWithPassword(username: string, password: string): Promise<LoginResult> {
  return toLoginResult(await apiFetch<SessionOrMfa>(`${CENTER_API}/auth/login`, json({ username, password })));
}

/** Only an account that turned on the optional second factor gets an MFA challenge (default: a session). */
export async function loginWithGoogle(idToken: string): Promise<LoginResult> {
  return toLoginResult(await apiFetch<SessionOrMfa>(`${CENTER_API}/auth/google`, json({ id_token: idToken })));
}

export const loginWithBiometrics = (mfaToken: string, audio?: Blob, video?: Blob) =>
  apiForm<Session>(`${CENTER_API}/auth/login/biometric`, biometricForm({ mfa_token: mfaToken }, audio, video));

/** Sign in with ONE voice clip; the username is only sent after the server asked for it. */
export const loginWithVoice = (audio: Blob, username?: string) =>
  apiForm<Session>(`${CENTER_API}/auth/login/voice`, biometricForm({ username: username?.trim() || undefined }, audio));

/** Sign in with ONE face-only webcam clip (no audio); the username is only sent after the server asked for it. */
export const loginWithWebcam = (video: Blob, username?: string) =>
  apiForm<Session>(`${CENTER_API}/auth/login/webcam`, biometricForm({ username: username?.trim() || undefined }, undefined, video));

const NEW_USERNAME_KEY = "center.newUsername";

/** Remember an auto-generated username for a one-time notice (best effort: storage may be blocked). */
export function rememberNewUsername(username: string): void {
  try {
    window.sessionStorage.setItem(NEW_USERNAME_KEY, username);
  } catch {
    /* the notice is optional */
  }
}

/** Read and clear the one-time notice; always plain text. */
export function takeNewUsername(): string | null {
  try {
    const value = window.sessionStorage.getItem(NEW_USERNAME_KEY);
    window.sessionStorage.removeItem(NEW_USERNAME_KEY);
    return value;
  } catch {
    return null;
  }
}

export interface CombinedRegistration {
  username?: string;
  password?: string;
  googleIdToken?: string;
  voiceAudio?: Blob;
  webcamVideo?: Blob;
}

/** Register with any mix of methods in one all-or-nothing request; only the given methods are sent. */
export async function registerCombined(input: CombinedRegistration): Promise<Session> {
  assertBlobSizes(input.voiceAudio, input.webcamVideo);
  const form = new FormData();
  const username = input.username?.trim();
  if (username) form.append("username", username);
  if (input.password !== undefined) form.append("password", input.password);
  if (input.googleIdToken) form.append("google_id_token", input.googleIdToken);
  if (input.voiceAudio) form.append("voice_audio", input.voiceAudio, "voice.webm");
  if (input.webcamVideo) form.append("webcam_video", input.webcamVideo, "webcam.webm");
  return apiForm<Session>(`${CENTER_API}/auth/register/combined`, form);
}

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

export const unlinkGoogle = (password?: string) =>
  apiFetch<unknown>(`${CENTER_API}/auth/me/google`, { method: "DELETE", body: JSON.stringify({ password }) });

export const deleteAccount = (password?: string) =>
  apiFetch<void>(`${CENTER_API}/auth/me`, { method: "DELETE", body: JSON.stringify({ password }) });

export const saveVoice = (audio: Blob, password?: string) =>
  apiForm<MethodsStatus>(`${CENTER_API}/auth/me/voice`, biometricForm({ password }, audio));

export const saveWebcam = (video: Blob, password?: string) =>
  apiForm<MethodsStatus>(`${CENTER_API}/auth/me/webcam`, biometricForm({ password }, undefined, video));

export const removeVoice = (password?: string) =>
  apiForm<MethodsStatus>(`${CENTER_API}/auth/me/voice`, biometricForm({ password }), { method: "DELETE" });

export const removeWebcam = (password?: string) =>
  apiForm<MethodsStatus>(`${CENTER_API}/auth/me/webcam`, biometricForm({ password }), { method: "DELETE" });

export const setBiometric2fa = (enabled: boolean, password?: string) =>
  apiForm<unknown>(
    `${CENTER_API}/auth/me/biometric-2fa`,
    biometricForm({ enabled: String(enabled), password }),
    { method: "PUT" },
  );
