export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
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
  "/api/center/auth/login/biometric-only",
  "/api/center/auth/register",
  "/api/center/auth/google",
  "/api/center/auth/logout",
  REFRESH_PATH,
]);

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
    if (response.status === 401 && !retried && !NO_REFRESH_PATHS.has(pathOf(path))) {
      if (await refreshSession()) return send<T>(path, init, isForm, true);
    }
    throw new ApiError(response.status, await errorMessage(response));
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

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return "Please check the fields and try again";
  } catch {
    // body was not JSON
  }
  return `Request failed (${response.status})`;
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
