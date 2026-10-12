import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, setCsrfToken } from "@sn/api";
import * as auth from "../app/lib/auth";
import { postLoginTarget } from "../app/lib/navigate";
import { jsonResponse, me, mockFetch, session } from "./helpers";

beforeEach(() => {
  setCsrfToken(null);
  vi.unstubAllGlobals();
});

describe("safeNextPath (open redirect guard)", () => {
  it.each(["/", "/chat", "/account?tab=1", "/a/b#c"])("keeps %s", (path) => {
    expect(auth.safeNextPath(path)).toBe(path);
  });

  it.each([
    null,
    undefined,
    "",
    "chat",
    "//evil.com",
    "/\\evil.com",
    "https://evil.com",
    "javascript:alert(1)",
    "/ok\\..\\evil",
    "/line\nbreak",
    "/\tx",
  ])("falls back to / for %j", (path) => {
    expect(auth.safeNextPath(path)).toBe("/");
  });

  it("reads the next query parameter from the location", () => {
    window.history.pushState({}, "", "/login?next=%2Faccount");
    expect(postLoginTarget()).toBe("/account");
    window.history.pushState({}, "", "/login?next=%2F%2Fevil.com");
    expect(postLoginTarget()).toBe("/");
    window.history.pushState({}, "", "/login");
    expect(postLoginTarget()).toBe("/");
  });
});

describe("password policy", () => {
  it("reports each rule", () => {
    expect(auth.isPasswordValid("short")).toBe(false);
    expect(auth.isPasswordValid("long enough")).toBe(true);
    expect(auth.isPasswordValid("x".repeat(129))).toBe(false);
    expect(auth.isPasswordValid("x".repeat(128))).toBe(true);
  });
});

describe("errorText", () => {
  it("maps 429 and passes through other messages", () => {
    expect(auth.errorText(new ApiError(429, "slow"))).toBe("Thử quá nhiều lần, hãy thử lại sau");
    expect(auth.errorText(new ApiError(400, "bad"))).toBe("bad");
    expect(auth.errorText("weird")).toBe("Có lỗi xảy ra, hãy thử lại");
  });
});

describe("blob limits", () => {
  it("rejects oversized recordings", () => {
    const big = (bytes: number) => ({ size: bytes }) as Blob;
    expect(() => auth.assertBlobSizes(big(auth.MAX_AUDIO_BYTES + 1))).toThrow("3 MB");
    expect(() => auth.assertBlobSizes(undefined, big(auth.MAX_VIDEO_BYTES + 1))).toThrow("15 MB");
    expect(() => auth.assertBlobSizes(big(1), big(1))).not.toThrow();
  });
});

describe("API helpers", () => {
  it("login returns an mfa step or a session", async () => {
    mockFetch(() => jsonResponse({ mfa_required: true, mfa_token: "t" }));
    expect(await auth.loginWithPassword("a", "b")).toEqual({ kind: "mfa", mfaToken: "t" });
    mockFetch(() => jsonResponse(session));
    expect(await auth.loginWithPassword("a", "b")).toEqual({ kind: "session", session });
  });

  it("sends biometric multipart bodies with csrf for account calls", async () => {
    setCsrfToken("tok");
    const fetchMock = mockFetch(() => jsonResponse({}));
    const audio = new Blob(["a"]);
    await auth.loginWithBiometrics("mfa", audio, undefined);
    await auth.loginWithBiometricsOnly("ann", audio, new Blob(["v"]));
    await auth.enrollBiometrics("pw", audio);
    await auth.setBiometricLogin(true, "pw");
    await auth.deleteBiometrics();
    const bodies = fetchMock.mock.calls.map(([, init]) => init.body as FormData);
    expect(bodies[0].get("mfa_token")).toBe("mfa");
    expect(bodies[0].get("audio")).toBeInstanceOf(File);
    expect(bodies[1].get("username")).toBe("ann");
    expect(bodies[1].get("video")).toBeInstanceOf(File);
    expect(bodies[2].get("password")).toBe("pw");
    expect(bodies[3].get("enabled")).toBe("true");
    expect(fetchMock.mock.calls[3][1].method).toBe("PUT");
    expect(bodies[4].has("password")).toBe(false);
    expect(fetchMock.mock.calls[4][1].method).toBe("DELETE");
  });

  it("covers the JSON endpoints", async () => {
    const fetchMock = mockFetch((url) => (url.endsWith("/auth/me") && !fetchMock.mock.calls.at(-1)?.[1].method ? jsonResponse(me) : jsonResponse(session)));
    await auth.registerAccount("a", "pw");
    await auth.loginWithGoogle("idt");
    await auth.changePassword("new", "old");
    await auth.linkGoogle("idt", "pw");
    await auth.getAuthConfig();
    const bodies = fetchMock.mock.calls.map(([, init]) => init.body);
    expect(bodies[1]).toBe(JSON.stringify({ id_token: "idt" }));
    expect(bodies[2]).toBe(JSON.stringify({ new_password: "new", current_password: "old" }));
  });

  it("google login reports a pending second factor instead of a session", async () => {
    mockFetch(() => jsonResponse({ mfa_required: true, mfa_token: "tok" }));
    await expect(auth.loginWithGoogle("idt")).resolves.toEqual({ kind: "mfa", mfaToken: "tok" });
  });

  it("google login returns the session when no second factor is needed", async () => {
    mockFetch(() => jsonResponse(session));
    await expect(auth.loginWithGoogle("idt")).resolves.toEqual({ kind: "session", session });
  });

  it("delete and logout use the right verbs", async () => {
    const fetchMock = mockFetch(() => jsonResponse(null, 204));
    await auth.deleteAccount("pw");
    await auth.logout();
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
    expect(fetchMock.mock.calls[0][1].body).toBe(JSON.stringify({ password: "pw" }));
    expect(fetchMock.mock.calls[1][0]).toBe("/api/center/auth/logout");
  });
});

describe("loadMe", () => {
  it("returns the account, refreshing once on 401", async () => {
    mockFetch(() => jsonResponse(me));
    expect(await auth.loadMe()).toEqual(me);

    let refreshed = false;
    mockFetch((url) => {
      if (url.endsWith("/refresh")) {
        refreshed = true;
        return jsonResponse(session);
      }
      return refreshed ? jsonResponse(me) : jsonResponse({ detail: "x" }, 401);
    });
    expect(await auth.loadMe()).toEqual(me);
  });

  it("returns null when signed out and throws other errors", async () => {
    mockFetch(() => jsonResponse({ detail: "x" }, 401));
    expect(await auth.loadMe()).toBeNull();
    mockFetch((url) => (url.endsWith("/refresh") ? jsonResponse(session) : jsonResponse({ detail: "x" }, 401)));
    expect(await auth.loadMe()).toBeNull();
    mockFetch(() => jsonResponse({ detail: "boom" }, 500));
    await expect(auth.loadMe()).rejects.toThrow("boom");
  });
});
