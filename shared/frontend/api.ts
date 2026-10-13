export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    /** Parsed JSON error body (undefined when the body was not JSON). */
    public readonly body?: unknown,
  ) {
    super(message);
  }
}

const CENTER_PREFIX = "/api/center/";
const CSRF_HEADER = "X-CSRF-Token";
const CSRF_STORAGE_KEY = "sn_csrf_token";
const REFRESH_PATH = "/api/center/auth/refresh";
// Calls that report a missing/invalid session themselves; a 401 there must not trigger a refresh.
const NO_REFRESH_PATHS = new Set([
  "/api/center/auth/me",
  "/api/center/auth/login",
  "/api/center/auth/login/biometric",
  "/api/center/auth/login/voice",
  "/api/center/auth/login/webcam",
  "/api/center/auth/login/totp",
  "/api/center/auth/register/combined",
  "/api/center/auth/register",
  "/api/center/auth/google",
  "/api/center/auth/passkey/options",
  "/api/center/auth/passkey/login",
  "/api/center/auth/register/passkey/options",
  "/api/center/auth/logout",
  "/api/center/auth/email/login/request",
  "/api/center/auth/email/login/verify",
  "/api/center/auth/email/login/magic",
  "/api/center/auth/phone/login/request",
  "/api/center/auth/phone/login/verify",
  "/api/center/auth/qr/start",
  "/api/center/auth/qr/poll",
  "/api/center/auth/liveness/challenge",
  "/api/center/auth/email/verify",
  "/api/center/auth/password/forgot",
  "/api/center/auth/password/reset",
  REFRESH_PATH,
]);

/** The re-authentication methods a 401 asks for ({detail, reauth:[...]}), or null for any other error. */
export function reauthRequired(error: unknown): string[] | null {
  if (!(error instanceof ApiError) || error.status !== 401) return null;
  const list = (error.body as { reauth?: unknown } | undefined)?.reauth;
  if (!Array.isArray(list)) return null;
  return list.filter((item): item is string => typeof item === "string");
}

let csrfToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;

/** Remembers the CSRF token of the current session (null forgets it). */
export function setCsrfToken(token: string | null): void {
  csrfToken = token;
  try {
    if (token) sessionStorage.setItem(CSRF_STORAGE_KEY, token);
    else sessionStorage.removeItem(CSRF_STORAGE_KEY);
  } catch {
    // no sessionStorage (SSR, privacy mode): the module variable is enough
  }
}

function currentCsrfToken(): string | null {
  if (csrfToken) return csrfToken;
  try {
    csrfToken = sessionStorage.getItem(CSRF_STORAGE_KEY);
  } catch {
    // ignore, see setCsrfToken
  }
  return csrfToken;
}

function rememberCsrf(body: unknown): void {
  if (body && typeof body === "object" && "csrf_token" in body) {
    const token = (body as { csrf_token: unknown }).csrf_token;
    if (typeof token === "string" && token) setCsrfToken(token);
  }
}

function pathOf(path: string): string {
  return path.split(/[?#]/, 1)[0];
}

async function send<T>(path: string, init: RequestInit, isForm: boolean, retried = false): Promise<T> {
  const headers: Record<string, string> = isForm ? {} : { "Content-Type": "application/json" };
  Object.assign(headers, init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  if (method !== "GET" && path.startsWith(CENTER_PREFIX)) {
    const token = currentCsrfToken();
    if (token && !(CSRF_HEADER in headers)) headers[CSRF_HEADER] = token;
  }
  const response = await fetch(path, { ...init, credentials: "include", headers });
  if (!response.ok) {
    const body = await readJson(response);
    const error = new ApiError(response.status, errorMessage(response.status, body), body);
    // A step-up request is not an expired session: no refresh, no retry.
    if (response.status === 401 && !retried && !reauthRequired(error) && !NO_REFRESH_PATHS.has(pathOf(path))) {
      if (await refreshSession()) return send<T>(path, init, isForm, true);
    }
    throw error;
  }
  if (response.status === 204) return undefined as T;
  const body = (await response.json()) as T;
  if (path.startsWith(CENTER_PREFIX)) rememberCsrf(body);
  return body;
}

/** JSON fetch against the gateway; sends the auth cookie and throws ApiError on non-2xx. */
export function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  return send<T>(path, init, false);
}

/** Multipart upload (no JSON content type; the browser sets the boundary). */
export function apiForm<T>(path: string, form: FormData, init: RequestInit = {}): Promise<T> {
  return send<T>(path, { method: "POST", ...init, body: form }, true);
}

/** Renews the access cookie from the refresh cookie. Parallel callers share one request. */
export function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function doRefresh(): Promise<boolean> {
  try {
    const response = await fetch(REFRESH_PATH, { method: "POST", credentials: "include" });
    if (!response.ok) return false;
    rememberCsrf(await response.json().catch(() => null));
    return true;
  } catch {
    return false;
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined; // body was not JSON
  }
}

function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "Please check the fields and try again";
  return `Request failed (${status})`;
}

export interface User {
  id: number;
  username: string;
}

export const CENTER_API = "/api/center";
export const CHAT_API = "/api/chat";

export function fetchCurrentUser(): Promise<User> {
  return apiFetch<User>(`${CENTER_API}/auth/me`);
}

/**
 * The signed-in user, or null when not signed in (401). A 401 first tries the refresh cookie once.
 * Other failures are thrown.
 */
export async function loadSession(): Promise<User | null> {
  try {
    return await fetchCurrentUser();
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
  }
  if (!(await refreshSession())) return null;
  try {
    return await fetchCurrentUser();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}
