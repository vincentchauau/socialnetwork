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
  email_verified: boolean;
  has_password: boolean;
  google_linked: boolean;
  voice_login: boolean;
  webcam_login: boolean;
  has_audio: boolean;
  has_face: boolean;
  require_biometric_2fa: boolean;
  passkey_count: number;
  passkeys: PasskeyItem[];
  totp_enabled: boolean;
  recovery_codes_left: number;
  csrf_token: string;
}

export interface MethodsStatus {
  email_verified: boolean;
  has_password: boolean;
  google_linked: boolean;
  voice_login: boolean;
  webcam_login: boolean;
  has_audio: boolean;
  has_face: boolean;
  require_biometric_2fa: boolean;
  passkey_count: number;
  passkeys: PasskeyItem[];
  totp_enabled: boolean;
  recovery_codes_left: number;
}

export interface PasskeyItem {
  id: number;
  name: string;
  created_at: string;
  last_used_at: string | null;
  backed_up: boolean;
  transports: string[];
}

/** WebAuthn options (opaque JSON from the server) plus the signed token that binds the ceremony. */
export interface PasskeyChallenge<T> {
  options: T;
  challenge_token: string;
}

export interface PasskeyList {
  passkeys: PasskeyItem[];
}

export interface AuthConfig {
  google_client_id: string | null;
  biometrics_enabled: boolean;
  email_enabled: boolean;
}

export const NO_CONFIG: AuthConfig = { google_client_id: null, biometrics_enabled: false, email_enabled: false };

export type MfaFactor = "totp" | "biometric";
export interface MfaChallenge {
  mfaToken: string;
  factors: MfaFactor[];
}

export type LoginResult = { kind: "session"; session: Session } | ({ kind: "mfa" } & MfaChallenge);

export const MAX_PASSKEYS = 10;
export const PASSKEY_LIMIT_MESSAGE = "Tối đa 10 Passkey cho mỗi tài khoản";
export const RECOVERY_CODE_COUNT = 10;

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

const PASSKEY_LIMIT = "Passkey limit reached";
export const USERNAME_NEEDED = "Enter your username";
const VOICE_TAKEN = "This voice is already registered";
const VOICE_TAKEN_HELP = "Giọng nói này đã được đăng ký cho một tài khoản khác, hãy đăng nhập hoặc dùng giọng khác.";

export function errorText(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) return "Thử quá nhiều lần, hãy thử lại sau";
  if (error instanceof ApiError && error.status === 409 && error.message === PASSKEY_LIMIT) return PASSKEY_LIMIT_MESSAGE;
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

type SessionOrMfa = Session | { mfa_required: true; mfa_token: string; factors?: MfaFactor[] };

function toLoginResult(body: SessionOrMfa): LoginResult {
  if ("mfa_required" in body && body.mfa_required) {
    // Old servers send no `factors`: the only second factor then was the biometric one.
    const factors = body.factors?.length ? body.factors : (["biometric"] as MfaFactor[]);
    return { kind: "mfa", mfaToken: body.mfa_token, factors };
  }
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

/** Second factor with an authenticator code or (instead) a one-time recovery code. */
export const loginWithTotp = (mfaToken: string, proof: { code: string } | { recoveryCode: string }) =>
  apiFetch<Session>(
    `${CENTER_API}/auth/login/totp`,
    json("code" in proof ? { mfa_token: mfaToken, code: proof.code } : { mfa_token: mfaToken, recovery_code: proof.recoveryCode }),
  );

/** Sign in with ONE voice clip; the username is only sent after the server asked for it. */
export async function loginWithVoice(audio: Blob, username?: string): Promise<LoginResult> {
  const form = biometricForm({ username: username?.trim() || undefined }, audio);
  return toLoginResult(await apiForm<SessionOrMfa>(`${CENTER_API}/auth/login/voice`, form));
}

/** Sign in with ONE face-only webcam clip (no audio); the username is only sent after the server asked for it. */
export async function loginWithWebcam(video: Blob, username?: string): Promise<LoginResult> {
  const form = biometricForm({ username: username?.trim() || undefined }, undefined, video);
  return toLoginResult(await apiForm<SessionOrMfa>(`${CENTER_API}/auth/login/webcam`, form));
}

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

const VERIFY_EMAIL_KEY = "center.verifyEmail";

/** Remember the address a verification mail was sent to, for a one-time notice (best effort). */
export function rememberVerificationEmail(email: string): void {
  try {
    window.sessionStorage.setItem(VERIFY_EMAIL_KEY, email);
  } catch {
    /* the notice is optional */
  }
}

/** Read and clear the one-time notice; always plain text. */
export function takeVerificationEmail(): string | null {
  try {
    const value = window.sessionStorage.getItem(VERIFY_EMAIL_KEY);
    window.sessionStorage.removeItem(VERIFY_EMAIL_KEY);
    return value;
  } catch {
    return null;
  }
}

export interface CombinedRegistration {
  username?: string;
  email?: string;
  password?: string;
  googleIdToken?: string;
  voiceAudio?: Blob;
  webcamVideo?: Blob;
  passkeyCredential?: unknown;
  passkeyChallengeToken?: string;
}

/** Register with any mix of methods in one all-or-nothing request; only the given methods are sent. */
export async function registerCombined(input: CombinedRegistration): Promise<Session> {
  assertBlobSizes(input.voiceAudio, input.webcamVideo);
  const form = new FormData();
  const username = input.username?.trim();
  if (username) form.append("username", username);
  const email = input.email?.trim();
  if (email) form.append("email", email);
  if (input.password !== undefined) form.append("password", input.password);
  if (input.googleIdToken) form.append("google_id_token", input.googleIdToken);
  if (input.voiceAudio) form.append("voice_audio", input.voiceAudio, "voice.webm");
  if (input.webcamVideo) form.append("webcam_video", input.webcamVideo, "webcam.webm");
  if (input.passkeyCredential !== undefined && input.passkeyChallengeToken) {
    form.append("passkey_credential", JSON.stringify(input.passkeyCredential));
    form.append("passkey_challenge_token", input.passkeyChallengeToken);
  }
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

/* ---- Passkey (WebAuthn): the browser/device does the biometrics, the server only sees public keys ---- */

export const passkeyLoginOptions = <T = unknown>() =>
  apiFetch<PasskeyChallenge<T>>(`${CENTER_API}/auth/passkey/options`, { method: "POST" });

export const loginWithPasskey = (credential: unknown, challengeToken: string) =>
  apiFetch<Session>(`${CENTER_API}/auth/passkey/login`, json({ credential, challenge_token: challengeToken }));

export const passkeyRegisterOptions = <T = unknown>(username?: string) => {
  const name = username?.trim();
  return apiFetch<PasskeyChallenge<T>>(`${CENTER_API}/auth/register/passkey/options`, json(name ? { username: name } : {}));
};

export const myPasskeyOptions = <T = unknown>(password?: string) =>
  apiFetch<PasskeyChallenge<T>>(`${CENTER_API}/auth/me/passkeys/options`, json({ password }));

export const addPasskey = (credential: unknown, challengeToken: string, name?: string) =>
  apiFetch<PasskeyList>(
    `${CENTER_API}/auth/me/passkeys`,
    json({ credential, challenge_token: challengeToken, name: name?.trim() || undefined }),
  );

export const renamePasskey = (id: number, name: string) =>
  apiFetch<unknown>(`${CENTER_API}/auth/me/passkeys/${id}`, { method: "PATCH", body: JSON.stringify({ name }) });

export const deletePasskey = (id: number, password?: string) =>
  apiFetch<PasskeyList>(`${CENTER_API}/auth/me/passkeys/${id}`, { method: "DELETE", body: JSON.stringify({ password }) });

/* ---- Email: verification, sign-in (code or magic link), password reset ---- */

export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const isEmailValid = (email: string): boolean => email.length <= 254 && EMAIL_PATTERN.test(email.trim());
export const EMAIL_INVALID = "Email không hợp lệ";
export const NEUTRAL_SIGN_IN_MESSAGE = "Nếu email này thuộc một tài khoản, chúng tôi đã gửi mã và liên kết đăng nhập.";
export const NEUTRAL_RESET_MESSAGE = "Nếu email này thuộc một tài khoản, chúng tôi đã gửi liên kết đặt lại mật khẩu.";

export interface VerifiedEmail {
  email: string;
  email_verified: boolean;
}

export const requestEmailLogin = (email: string) =>
  apiFetch<unknown>(`${CENTER_API}/auth/email/login/request`, json({ email: email.trim() }));

export async function verifyEmailLogin(email: string, code: string): Promise<LoginResult> {
  return toLoginResult(
    await apiFetch<SessionOrMfa>(`${CENTER_API}/auth/email/login/verify`, json({ email: email.trim(), code: code.trim() })),
  );
}

export async function loginWithMagicLink(token: string): Promise<LoginResult> {
  return toLoginResult(await apiFetch<SessionOrMfa>(`${CENTER_API}/auth/email/login/magic`, json({ token })));
}

export const forgotPassword = (email: string) =>
  apiFetch<unknown>(`${CENTER_API}/auth/password/forgot`, json({ email: email.trim() }));

export const resetPassword = (token: string, newPassword: string) =>
  apiFetch<unknown>(`${CENTER_API}/auth/password/reset`, json({ token, new_password: newPassword }));

export const verifyEmailToken = (token: string) =>
  apiFetch<VerifiedEmail>(`${CENTER_API}/auth/email/verify`, json({ token }));

export const verifyEmailCode = (code: string) =>
  apiFetch<VerifiedEmail>(`${CENTER_API}/auth/email/verify`, json({ code: code.trim() }));

export const setMyEmail = (email: string, password?: string) =>
  apiFetch<unknown>(`${CENTER_API}/auth/me/email`, json({ email: email.trim(), password }));

export const removeMyEmail = (password?: string) =>
  apiFetch<MethodsStatus>(`${CENTER_API}/auth/me/email`, { method: "DELETE", body: JSON.stringify({ password }) });

/* ---- TOTP second factor (authenticator app) + recovery codes ---- */

export interface TotpSetup {
  secret: string;
  otpauth_uri: string;
}

export interface RecoveryCodes {
  recovery_codes: string[];
}

export const totpSetup = (password?: string) =>
  apiFetch<TotpSetup>(`${CENTER_API}/auth/totp/setup`, json({ password }));

export async function totpEnable(code: string, password?: string): Promise<RecoveryCodes> {
  // The reply carries the re-issued session's csrf_token (apiFetch stores it); /auth/me confirms it before any further write.
  const result = await apiFetch<RecoveryCodes>(`${CENTER_API}/auth/totp/enable`, json({ code, password }));
  await fetchMe();
  return result;
}

/** `code` is a current authenticator code or an unused recovery code. */
export async function totpDisable(code: string, password?: string): Promise<void> {
  await apiFetch<void>(`${CENTER_API}/auth/totp`, { method: "DELETE", body: JSON.stringify({ code, password }) });
  // The server re-issues the session cookies (new access token, new CSRF token): fetch it before any further write.
  await fetchMe();
}

export const totpRegenerateRecoveryCodes = (code: string, password?: string) =>
  apiFetch<RecoveryCodes>(`${CENTER_API}/auth/totp/recovery-codes`, json({ code, password }));
