import { vi } from "vitest";

import type { Me } from "../app/lib/auth";

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>;

/** Replaces fetch with a handler; returns the mock so tests can inspect calls. */
export function mockFetch(handler: Handler) {
  const fn = vi.fn<(url: string, init: RequestInit) => Promise<Response>>((url, init) =>
    Promise.resolve(handler(url, init ?? {})),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

export const session = { id: 1, username: "ann", role: "user", csrf_token: "csrf-1" };

export const me: Me = {
  ...session,
  email: null,
  email_verified: false,
  has_password: true,
  google_linked: false,
  voice_login: false,
  webcam_login: false,
  has_audio: false,
  has_face: false,
  require_biometric_2fa: false,
  passkey_count: 0,
  passkeys: [],
  totp_enabled: false,
  recovery_codes_left: 0,
};

export function headerOf(init: RequestInit | undefined, name: string): string | undefined {
  return (init?.headers as Record<string, string> | undefined)?.[name];
}
