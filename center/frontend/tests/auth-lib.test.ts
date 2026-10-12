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
  it("password login returns the session", async () => {
    mockFetch(() => jsonResponse(session));
    expect(await auth.loginWithPassword("a", "b")).toEqual({ kind: "session", session });
  });

  it("password login reports a pending second factor instead of a session", async () => {
    mockFetch(() => jsonResponse({ mfa_required: true, mfa_token: "tok" }));
    expect(await auth.loginWithPassword("a", "b")).toEqual({ kind: "mfa", mfaToken: "tok" });
  });

  it("google login reports a pending second factor instead of a session", async () => {
    mockFetch(() => jsonResponse({ mfa_required: true, mfa_token: "tok" }));
    await expect(auth.loginWithGoogle("idt")).resolves.toEqual({ kind: "mfa", mfaToken: "tok" });
  });

  it("the second-factor call sends the mfa token and the recording to the biometric route", async () => {
    const fetchMock = mockFetch(() => jsonResponse(session));
    await auth.loginWithBiometrics("tok", new Blob(["a"]), new Blob(["v"]));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/center/auth/login/biometric");
    const body = init.body as FormData;
    expect(body.get("mfa_token")).toBe("tok");
    expect(body.get("audio")).toBeInstanceOf(File);
    expect(body.get("video")).toBeInstanceOf(File);
  });

  it("the second-factor switch and Google unlink use the right routes and verbs", async () => {
    setCsrfToken("tok");
    const fetchMock = mockFetch(() => jsonResponse({}));
    await auth.setBiometric2fa(true, "pw");
    await auth.unlinkGoogle("pw");
    const [[url1, init1], [url2, init2]] = fetchMock.mock.calls;
    expect(url1).toBe("/api/center/auth/me/biometric-2fa");
    expect(init1.method).toBe("PUT");
    expect((init1.body as FormData).get("enabled")).toBe("true");
    expect((init1.body as FormData).get("password")).toBe("pw");
    expect(url2).toBe("/api/center/auth/me/google");
    expect(init2.method).toBe("DELETE");
    expect(init2.body).toBe(JSON.stringify({ password: "pw" }));
  });

  it("voice and webcam sign-in send only their own clip (username only when given)", async () => {
    const fetchMock = mockFetch(() => jsonResponse(session));
    await auth.loginWithVoice(new Blob(["a"]));
    await auth.loginWithWebcam(new Blob(["v"]));
    const [[url1, init1], [url2, init2]] = fetchMock.mock.calls;
    expect(url1).toBe("/api/center/auth/login/voice");
    expect(url2).toBe("/api/center/auth/login/webcam");
    const voice = init1.body as FormData;
    const webcam = init2.body as FormData;
    expect(voice.has("username")).toBe(false);
    expect(voice.get("audio")).toBeInstanceOf(File);
    expect(voice.has("password")).toBe(false);
    expect(webcam.get("video")).toBeInstanceOf(File);
    expect(webcam.has("audio")).toBe(false);
    expect(webcam.has("username")).toBe(false);
  });

  it("combined registration sends only the chosen fields", async () => {
    const fetchMock = mockFetch(() => jsonResponse(session, 201));
    await auth.registerCombined({ username: "ann", password: "password1" });
    await auth.registerCombined({
      username: "ann",
      googleIdToken: "idt",
      voiceAudio: new Blob(["a"]),
      webcamVideo: new Blob(["v"]),
    });
    const [[url, first], [, second]] = fetchMock.mock.calls;
    expect(url).toBe("/api/center/auth/register/combined");
    const one = first.body as FormData;
    expect([...one.keys()].sort()).toEqual(["password", "username"]);
    const all = second.body as FormData;
    expect([...all.keys()].sort()).toEqual(["google_id_token", "username", "voice_audio", "webcam_video"]);
    expect(all.get("voice_audio")).toBeInstanceOf(File);
  });

  it("rejects oversized clips before sending", async () => {
    const fetchMock = mockFetch(() => jsonResponse(session));
    const big = { size: auth.MAX_VIDEO_BYTES + 1 } as Blob;
    await expect(auth.registerCombined({ username: "a", voiceAudio: big })).rejects.toThrow(/giọng nói quá lớn/);
    await expect(auth.registerCombined({ username: "a", webcamVideo: big })).rejects.toThrow(/quay phim quá lớn/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("account voice/webcam calls use the right routes, verbs and password field", async () => {
    setCsrfToken("tok");
    const fetchMock = mockFetch(() => jsonResponse({}));
    await auth.saveVoice(new Blob(["a"]), "pw");
    await auth.saveWebcam(new Blob(["v"]));
    await auth.removeVoice("pw");
    await auth.removeWebcam();
    const calls = fetchMock.mock.calls;
    expect(calls.map(([url, init]) => `${init.method} ${url}`)).toEqual([
      "POST /api/center/auth/me/voice",
      "POST /api/center/auth/me/webcam",
      "DELETE /api/center/auth/me/voice",
      "DELETE /api/center/auth/me/webcam",
    ]);
    const bodies = calls.map(([, init]) => init.body as FormData);
    expect(bodies[0].get("password")).toBe("pw");
    expect(bodies[0].get("audio")).toBeInstanceOf(File);
    expect(bodies[1].has("password")).toBe(false);
    expect(bodies[1].get("video")).toBeInstanceOf(File);
    expect(bodies[2].get("password")).toBe("pw");
    expect(bodies[3].has("password")).toBe(false);
    expect((calls[0][1].headers as Record<string, string>)["X-CSRF-Token"]).toBe("tok");
  });

  it("covers the JSON endpoints", async () => {
    const fetchMock = mockFetch((url) => (url.endsWith("/auth/me") && !fetchMock.mock.calls.at(-1)?.[1].method ? jsonResponse(me) : jsonResponse(session)));
    await auth.loginWithGoogle("idt");
    await auth.changePassword("new", "old");
    await auth.linkGoogle("idt", "pw");
    await auth.getAuthConfig();
    const bodies = fetchMock.mock.calls.map(([, init]) => init.body);
    expect(bodies[0]).toBe(JSON.stringify({ id_token: "idt" }));
    expect(bodies[1]).toBe(JSON.stringify({ new_password: "new", current_password: "old" }));
  });

  it("google login returns the session", async () => {
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

describe("new-username notice storage", () => {
  it("stores a username once and clears it on read", () => {
    window.sessionStorage.clear();
    auth.rememberNewUsername("user-1a2b3c");
    expect(auth.takeNewUsername()).toBe("user-1a2b3c");
    expect(auth.takeNewUsername()).toBeNull();
  });

  it("never throws when storage is blocked", () => {
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(() => auth.rememberNewUsername("x")).not.toThrow();
    expect(auth.takeNewUsername()).toBeNull();
    set.mockRestore();
    get.mockRestore();
  });
});
