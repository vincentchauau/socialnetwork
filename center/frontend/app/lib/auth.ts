import { ApiError, CENTER_API, apiFetch, apiForm, refreshSession } from "@sn/api";

import { getPasskeyCredential } from "./passkey";

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
  /** Masked number (e.g. "+84•••••567") or null; absent on servers without phone sign-in. */
  phone?: string | null;
  phone_verified?: boolean;
  csrf_token: string;
  username_changed_at?: string | null;
  can_rename_after?: string | null;
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
  phone_enabled: boolean;
  liveness_enabled: boolean;
  liveness_required: boolean;
}

export const NO_CONFIG: AuthConfig = {
  google_client_id: null,
  biometrics_enabled: false,
  email_enabled: false,
  phone_enabled: false,
  liveness_enabled: false,
  liveness_required: false,
};

/** The part of the config the webcam recorder needs. */
export type LivenessSetting = Pick<AuthConfig, "liveness_enabled" | "liveness_required">;

export type MfaFactor = "totp" | "biometric";
export interface MfaChallenge {
  mfaToken: string;
  factors: MfaFactor[];
}

export type LoginResult = { kind: "session"; session: Session } | ({ kind: "mfa" } & MfaChallenge);

export const MAX_PASSKEYS = 10;
export const PASSKEY_LIMIT_MESSAGE = "Tối đa 10 Passkey cho mỗi tài khoản";
export const RECOVERY_CODE_COUNT = 10;

export const PASSWORD_EXAMPLE = "123@Pass";
export const PASSWORD_MESSAGE = `Mật khẩu cần ${MIN_PASSWORD}-${MAX_PASSWORD} ký tự, gồm chữ thường, chữ hoa, số và ký tự đặc biệt`;

export interface PasswordChecks {
  length: boolean;
  lower: boolean;
  upper: boolean;
  digit: boolean;
  special: boolean;
}

/** The four character classes the server requires (it has the final say; same rule as app/passwords.py). */
export function passwordChecks(password: string): PasswordChecks {
  return {
    length: password.length >= MIN_PASSWORD && password.length <= MAX_PASSWORD,
    lower: /\p{Ll}/u.test(password),
    upper: /\p{Lu}/u.test(password),
    digit: /\p{Nd}/u.test(password),
    special: /[^\p{L}\p{N}]/u.test(password),
  };
}

export function isPasswordValid(password: string): boolean {
  return Object.values(passwordChecks(password)).every(Boolean);
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

/** Same set as the server's ALLOWED_SPECIALS. Not '@', spaces, separators (: | / \\ " ' < > ` * ? [ ] { } ( ) , ;) or non-ASCII. */
export const USERNAME_SPECIALS = "._-!#$%&+=^~";
const escapeForClass = (chars: string): string => chars.replace(/[\\\]^-]/g, "\\$&");
export const USERNAME_PATTERN = new RegExp(`^[A-Za-z0-9${escapeForClass(USERNAME_SPECIALS)}]{3,32}$`);
const USERNAME_ALNUM = /[A-Za-z0-9]/;
export const USERNAME_MESSAGE = `Tên đăng nhập gồm 3-32 ký tự: chữ, số và ${USERNAME_SPECIALS.split("").join(" ")} (cần ít nhất một chữ hoặc số)`;
export const USERNAME_AT_MESSAGE = "Tên đăng nhập không được chứa @ (để không bị nhầm với email)";
export const USERNAME_SPACE_MESSAGE = "Tên đăng nhập không được chứa khoảng trắng";
export const USERNAME_COOLDOWN_MESSAGE = "Bạn chỉ có thể đổi tên đăng nhập 30 ngày một lần";
export const USERNAME_TAKEN_MESSAGE = "Tên đăng nhập này đã có người dùng";
/** Capitals are kept as typed (uniqueness ignores case): only the characters and the length matter. */
export const isUsernameValid = (username: string): boolean => USERNAME_PATTERN.test(username) && USERNAME_ALNUM.test(username);

/** The message to show for a bad username, or null when it is fine. */
export function usernameProblem(username: string): string | null {
  if (username.includes("@")) return USERNAME_AT_MESSAGE;
  if (/\s/.test(username)) return USERNAME_SPACE_MESSAGE;
  return isUsernameValid(username) ? null : USERNAME_MESSAGE;
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError && /once every 30 days|can be changed again after/i.test(error.message)) return USERNAME_COOLDOWN_MESSAGE;
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

export const loginWithBiometrics = (mfaToken: string, audio?: Blob, video?: Blob, livenessToken?: string) =>
  apiForm<Session>(
    `${CENTER_API}/auth/login/biometric`,
    biometricForm({ mfa_token: mfaToken, liveness_token: livenessToken }, audio, video),
  );

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
export async function loginWithWebcam(video: Blob, username?: string, livenessToken?: string): Promise<LoginResult> {
  const form = biometricForm({ username: username?.trim() || undefined, liveness_token: livenessToken }, undefined, video);
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
  livenessToken?: string;
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
  if (input.livenessToken) form.append("liveness_token", input.livenessToken);
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

export async function changeUsername(username: string, password?: string): Promise<Session> {
  try {
    return await apiFetch<Session>(`${CENTER_API}/auth/me/username`, json({ username, password }));
  } catch (error) {
    // Only here: registration keeps showing the server's own wording for the same 409.
    if (error instanceof ApiError && error.status === 409 && error.message === "Username already taken") {
      throw new Error(USERNAME_TAKEN_MESSAGE);
    }
    throw error;
  }
}

export const linkGoogle = (idToken: string, password?: string) =>
  apiFetch<unknown>(`${CENTER_API}/auth/me/google`, json({ id_token: idToken, password }));

export const unlinkGoogle = (password?: string) =>
  apiFetch<unknown>(`${CENTER_API}/auth/me/google`, { method: "DELETE", body: JSON.stringify({ password }) });

export const deleteAccount = (password?: string) =>
  apiFetch<void>(`${CENTER_API}/auth/me`, { method: "DELETE", body: JSON.stringify({ password }) });

export const saveVoice = (audio: Blob, password?: string) =>
  apiForm<MethodsStatus>(`${CENTER_API}/auth/me/voice`, biometricForm({ password }, audio));

export const saveWebcam = (video: Blob, password?: string, livenessToken?: string) =>
  apiForm<MethodsStatus>(
    `${CENTER_API}/auth/me/webcam`,
    biometricForm({ password, liveness_token: livenessToken }, undefined, video),
  );

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

/* ---- Devices and sign-in sessions ---- */

export type SessionMethod = "password" | "google" | "email" | "passkey" | "voice" | "webcam";

export interface DeviceSession {
  id: number;
  current: boolean;
  created_at: string;
  last_seen_at: string;
  ip: string | null;
  user_agent: string | null;
  method: SessionMethod | string;
}

export const listSessions = () => apiFetch<DeviceSession[]>(`${CENTER_API}/auth/sessions`);

export const revokeSession = (id: number) => apiFetch<void>(`${CENTER_API}/auth/sessions/${id}`, { method: "DELETE" });

export const revokeOtherSessions = () =>
  apiFetch<{ revoked: number }>(`${CENTER_API}/auth/sessions/revoke-others`, { method: "POST" });

/* ---- Step-up (re-authentication) for accounts without a password ---- */

export type ReauthMethod = "passkey" | "google" | "email";

export interface Reauthed {
  fresh_until: string;
}

export const reauthMethods = () => apiFetch<{ methods: string[] }>(`${CENTER_API}/auth/reauth/methods`);

/** Passkey ceremony against the re-authentication endpoints (same shapes as passkey login). */
export async function reauthPasskey(): Promise<Reauthed> {
  const { options, challenge_token } = await apiFetch<PasskeyChallenge<unknown>>(
    `${CENTER_API}/auth/reauth/passkey/options`,
    { method: "POST" },
  );
  const credential = await getPasskeyCredential(options);
  return apiFetch<Reauthed>(`${CENTER_API}/auth/reauth/passkey/verify`, json({ credential, challenge_token }));
}

export const reauthGoogle = (idToken: string) =>
  apiFetch<Reauthed>(`${CENTER_API}/auth/reauth/google`, json({ id_token: idToken }));

export const reauthEmailRequest = () => apiFetch<unknown>(`${CENTER_API}/auth/reauth/email/request`, json({}));

export const reauthEmailVerify = (code: string) =>
  apiFetch<Reauthed>(`${CENTER_API}/auth/reauth/email/verify`, json({ code: code.trim() }));

/* ---- Webcam liveness: a short-lived challenge (2 actions) whose token is sent with the recorded video ---- */

export type LivenessAction = "blink" | "turn_left" | "turn_right" | "open_mouth";

export interface LivenessChallenge {
  challenge_token: string;
  actions: LivenessAction[];
  expires_in: number;
}

export const LIVENESS_LABEL: Record<LivenessAction, string> = {
  blink: "Nháy mắt",
  turn_left: "Quay mặt sang trái",
  turn_right: "Quay mặt sang phải",
  open_mouth: "Há miệng",
};

export const createLivenessChallenge = () =>
  apiFetch<LivenessChallenge>(`${CENTER_API}/auth/liveness/challenge`, json({}));

/* ---- Phone (SMS): sign-in by a 6-digit code and the account's own number ---- */

export const PHONE_PATTERN = /^\+[1-9]\d{7,14}$/;
export const PHONE_INVALID = "Số điện thoại không hợp lệ, hãy nhập dạng quốc tế, ví dụ +84901234567";
export const NEUTRAL_PHONE_MESSAGE = "Nếu số điện thoại này thuộc một tài khoản, chúng tôi đã gửi mã đăng nhập qua SMS.";
export const PHONE_SMS_WARNING = "SMS kém an toàn hơn Passkey hoặc ứng dụng xác thực (có thể bị đánh cắp SIM)";

/** Drops spaces, dots, dashes and brackets people type; the "+" and digits stay. */
export const normalizePhone = (phone: string): string => phone.replace(/[\s.\-()]/g, "");
export const isPhoneValid = (phone: string): boolean => PHONE_PATTERN.test(normalizePhone(phone));

export const requestPhoneLogin = (phone: string) =>
  apiFetch<unknown>(`${CENTER_API}/auth/phone/login/request`, json({ phone: normalizePhone(phone) }));

export async function verifyPhoneLogin(phone: string, code: string): Promise<LoginResult> {
  return toLoginResult(
    await apiFetch<SessionOrMfa>(`${CENTER_API}/auth/phone/login/verify`, json({ phone: normalizePhone(phone), code: code.trim() })),
  );
}

export const setMyPhone = (phone: string, password?: string) =>
  apiFetch<unknown>(`${CENTER_API}/auth/me/phone`, json({ phone: normalizePhone(phone), password }));

export const verifyMyPhone = (code: string) =>
  apiFetch<unknown>(`${CENTER_API}/auth/me/phone/verify`, json({ code: code.trim() }));

export const removeMyPhone = (password?: string) =>
  apiFetch<unknown>(`${CENTER_API}/auth/me/phone`, { method: "DELETE", body: JSON.stringify({ password }) });

/* ---- QR sign-in: the desktop shows a QR, a signed-in phone approves it ---- */

export interface QrStart {
  request_id: string;
  poll_token: string;
  verify_code: string;
  expires_in: number;
  qr_url: string;
}

export interface QrRequest {
  requester_ip: string | null;
  requester_user_agent: string | null;
  created_at: string;
  expires_in: number;
}

export type QrPollStatus = "pending" | "denied" | "expired";
export type QrPollResult = { kind: "status"; status: QrPollStatus } | LoginResult;

export const QR_EXPIRED_MESSAGE = "Yêu cầu đã hết hạn";
export const QR_WRONG_CODE_MESSAGE = "Mã xác nhận không đúng";

export const qrStart = () => apiFetch<QrStart>(`${CENTER_API}/auth/qr/start`, json({}));

const POLL_STATUSES: readonly string[] = ["pending", "denied", "expired"];

export async function qrPoll(requestId: string, pollToken: string): Promise<QrPollResult> {
  const body = await apiFetch<SessionOrMfa | { status: QrPollStatus }>(
    `${CENTER_API}/auth/qr/poll`,
    json({ request_id: requestId, poll_token: pollToken }),
  );
  if ("status" in body && POLL_STATUSES.includes(body.status)) return { kind: "status", status: body.status };
  return toLoginResult(body as SessionOrMfa);
}

const qrPath = (id: string, suffix = "") => `${CENTER_API}/auth/qr/${encodeURIComponent(id)}${suffix}`;

export const qrDetails = (id: string) => apiFetch<QrRequest>(qrPath(id));

export const qrApprove = (id: string, verifyCode: string) =>
  apiFetch<unknown>(qrPath(id, "/approve"), json({ verify_code: verifyCode.trim() }));

export const qrDeny = (id: string) => apiFetch<unknown>(qrPath(id, "/deny"), json({}));
