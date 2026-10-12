export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** JSON fetch against the gateway; sends the auth cookie and throws ApiError on non-2xx. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init.headers },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
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

/** The signed-in user, or null when not signed in (401). Other failures are thrown. */
export async function loadSession(): Promise<User | null> {
  try {
    return await fetchCurrentUser();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}
