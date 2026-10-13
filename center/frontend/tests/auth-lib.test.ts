import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, setCsrfToken } from "@sn/api";
import * as auth from "../app/lib/auth";
import { postLoginTarget } from "../app/lib/navigate";
import { headerOf, jsonResponse, me, mockFetch, session } from "./helpers";

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
    expect(auth.isPasswordValid("Sh-1a")).toBe(false); // too short
    expect(auth.isPasswordValid("Long-Enough-1")).toBe(true);
    expect(auth.isPasswordValid("long-enough-1")).toBe(false); // no uppercase
    expect(auth.isPasswordValid("LONG-ENOUGH-1")).toBe(false); // no lowercase
    expect(auth.isPasswordValid("Long-Enough-x")).toBe(false); // no digit
    expect(auth.isPasswordValid("LongEnough1x")).toBe(false); // no special character
    expect(auth.isPasswordValid("Mật-Khẩu-Dài-1")).toBe(true); // accents are allowed
    expect(auth.isPasswordValid("Aa1-".repeat(33))).toBe(false); // 132 characters: too long
    expect(auth.isPasswordValid("Aa1-".repeat(32))).toBe(true); // exactly 128
    expect(auth.passwordChecks("abc")).toEqual({ length: false, lower: true, upper: false, digit: false, special: false });
  });
});

describe("username rule", () => {
  it("accepts capitals (the server lowercases) but not other characters or bad lengths", () => {
    expect(auth.isUsernameValid("Username123")).toBe(true);
    expect(auth.isUsernameValid("an.nguyen_01-x")).toBe(true);
    expect(auth.isUsernameValid("ab")).toBe(false);
    expect(auth.isUsernameValid("a".repeat(33))).toBe(false);
    expect(auth.isUsernameValid("has space")).toBe(false);
    expect(auth.isUsernameValid("Nguyễn")).toBe(false);
  });

  it("accepts every allowed special character, anywhere", () => {
    for (const char of auth.USERNAME_SPECIALS) {
      expect(auth.isUsernameValid(`Us${char}er9`)).toBe(true);
      expect(auth.isUsernameValid(`${char}ab`)).toBe(true);
    }
    expect(auth.USERNAME_SPECIALS).toBe("._-!#$%&+=^~@");
    expect(auth.isUsernameValid("User@123")).toBe(true);
    for (const name of ["a@b.co", "@name1", "name@"]) expect(auth.isUsernameValid(name)).toBe(true);
  });

  it("treats @ as an ordinary character, including names that look like an email", () => {
    for (const name of ["User@123", "a@b.co", "@name1", "name@", "bob@example.com"]) {
      expect(auth.isUsernameValid(name)).toBe(true);
      expect(auth.usernameProblem(name)).toBeNull();
    }
    expect(auth.isUsernameValid("@@@")).toBe(false);
    expect(auth.PASSWORD_EXAMPLE).toBe("User@123");
  });

  it("refuses separators, metacharacters, control and look-alike characters", () => {
    for (const bad of ["a:bc", "a|bc", "a/bc", "a\\bc", 'a"bc', "a'bc", "a<b>", "a`bc", "a*bc", "a?bc", "a[b]", "a{b}", "a(b)", "a,bc", "a;bc", "a\tb", "a\nb", "аdmin"]) {
      expect(auth.isUsernameValid(bad)).toBe(false);
    }
  });

  it("needs at least one letter or digit", () => {
    for (const bad of ["...", "---", "!!!", "_._", "~~~"]) expect(auth.isUsernameValid(bad)).toBe(false);
    expect(auth.isUsernameValid("..1")).toBe(true);
  });

  it("explains a rejected name: spaces, then the general rule", () => {
    expect(auth.usernameProblem("a@b.co")).toBeNull();
    expect(auth.usernameProblem("has space")).toBe(auth.USERNAME_SPACE_MESSAGE);
    expect(auth.usernameProblem("ab")).toBe(auth.USERNAME_MESSAGE);
    expect(auth.usernameProblem("!!!")).toBe(auth.USERNAME_MESSAGE);
    expect(auth.usernameProblem("Ok!name")).toBeNull();
    expect(auth.USERNAME_MESSAGE).toContain("! # $ % & + = ^ ~");
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
    expect(await auth.loginWithPassword("a", "b")).toEqual({ kind: "mfa", mfaToken: "tok", factors: ["biometric"] });
  });

  it("keeps the factors the server lists and treats an empty list as the old biometric default", async () => {
    mockFetch(() => jsonResponse({ mfa_required: true, mfa_token: "tok", factors: ["totp", "biometric"] }));
    expect(await auth.loginWithPassword("a", "b")).toEqual({ kind: "mfa", mfaToken: "tok", factors: ["totp", "biometric"] });
    mockFetch(() => jsonResponse({ mfa_required: true, mfa_token: "tok", factors: [] }));
    expect(await auth.loginWithPassword("a", "b")).toMatchObject({ factors: ["biometric"] });
  });

  it("google login reports a pending second factor instead of a session", async () => {
    mockFetch(() => jsonResponse({ mfa_required: true, mfa_token: "tok" }));
    await expect(auth.loginWithGoogle("idt")).resolves.toEqual({ kind: "mfa", mfaToken: "tok", factors: ["biometric"] });
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
    await auth.registerCombined({ username: "ann", password: "Password-1x" });
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

describe("TOTP helpers", () => {
  const bodyOf = (fn: ReturnType<typeof mockFetch>) => JSON.parse(String(fn.mock.calls[0][1].body));

  it("login sends the code or the recovery code, never both", async () => {
    let fn = mockFetch(() => jsonResponse(session));
    await auth.loginWithTotp("tok", { code: "123456" });
    expect(fn.mock.calls[0][0]).toBe("/api/center/auth/login/totp");
    expect(bodyOf(fn)).toEqual({ mfa_token: "tok", code: "123456" });
    fn = mockFetch(() => jsonResponse(session));
    await auth.loginWithTotp("tok", { recoveryCode: "abcd-1234" });
    expect(bodyOf(fn)).toEqual({ mfa_token: "tok", recovery_code: "abcd-1234" });
  });

  it("setup, enable, disable and regenerate use the reauth password like the other sensitive calls", async () => {
    const fn = mockFetch((url, init) =>
      init.method === "DELETE" ? jsonResponse(null, 204) : jsonResponse({ secret: "S", otpauth_uri: "u", recovery_codes: ["a"] }),
    );
    await auth.totpSetup("pw");
    await auth.totpEnable("123456", "pw");
    await auth.totpRegenerateRecoveryCodes("123456", "pw");
    await auth.totpDisable("abc", "pw");
    const sent = fn.mock.calls.filter(([url]) => !url.endsWith("/auth/me")).map(([url, init]) => [url, init.method, JSON.parse(String(init.body))]);
    expect(sent).toEqual([
      ["/api/center/auth/totp/setup", "POST", { password: "pw" }],
      ["/api/center/auth/totp/enable", "POST", { code: "123456", password: "pw" }],
      ["/api/center/auth/totp/recovery-codes", "POST", { code: "123456", password: "pw" }],
      ["/api/center/auth/totp", "DELETE", { code: "abc", password: "pw" }],
    ]);
  });

  it("disabling refreshes /auth/me so the next write carries the re-issued CSRF token", async () => {
    setCsrfToken("old-csrf");
    const fn = mockFetch((url, init) => {
      if (init.method === "DELETE") return jsonResponse(null, 204);
      if (url.endsWith("/auth/me")) return jsonResponse({ ...me, csrf_token: "new-csrf" });
      return jsonResponse({});
    });
    await auth.totpDisable("123456", "pw");
    await auth.logout();
    const logoutCall = fn.mock.calls.find(([url]) => url.endsWith("/auth/logout"))!;
    expect(headerOf(logoutCall[1], "X-CSRF-Token")).toBe("new-csrf");
    expect(headerOf(fn.mock.calls[0][1], "X-CSRF-Token")).toBe("old-csrf");
  });

  it("enabling stores the returned CSRF token and re-fetches /auth/me before the next write", async () => {
    setCsrfToken("old-csrf");
    const fn = mockFetch((url) => {
      if (url.endsWith("/totp/enable")) return jsonResponse({ recovery_codes: ["a"], csrf_token: "enabled-csrf" });
      if (url.endsWith("/auth/me")) return jsonResponse({ ...me, csrf_token: "me-csrf" });
      return jsonResponse({});
    });
    await auth.totpEnable("123456", "pw");
    expect(fn.mock.calls.some(([url]) => url.endsWith("/auth/me"))).toBe(true);
    await auth.logout();
    const logoutCall = fn.mock.calls.find(([url]) => url.endsWith("/auth/logout"))!;
    expect(headerOf(logoutCall[1], "X-CSRF-Token")).toBe("me-csrf");
  });

  it("voice and webcam sign-in report a pending second factor", async () => {
    mockFetch(() => jsonResponse({ mfa_required: true, mfa_token: "tok", factors: ["totp"] }));
    expect(await auth.loginWithVoice(new Blob(["a"]))).toEqual({ kind: "mfa", mfaToken: "tok", factors: ["totp"] });
    expect(await auth.loginWithWebcam(new Blob(["v"]))).toEqual({ kind: "mfa", mfaToken: "tok", factors: ["totp"] });
  });

  it("maps the passkey limit 409 to the Vietnamese text", () => {
    expect(auth.errorText(new ApiError(409, "Passkey limit reached"))).toBe("Tối đa 10 Passkey cho mỗi tài khoản");
  });
});
