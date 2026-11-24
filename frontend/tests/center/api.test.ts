import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, apiForm, loadSession, refreshSession, setCsrfToken } from "@sn/api";
import { headerOf, jsonResponse, mockFetch, session } from "./helpers";

const REFRESH = "/api/center/auth/refresh";

beforeEach(() => {
  setCsrfToken(null);
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("CSRF", () => {
  it("attaches the remembered token to non-GET center requests only", async () => {
    const fetchMock = mockFetch((url) => (url.endsWith("/auth/login") ? jsonResponse(session) : jsonResponse({})));
    await apiFetch("/api/center/auth/login", { method: "POST", body: "{}" });
    await apiFetch("/api/center/auth/me/password", { method: "POST", body: "{}" });
    await apiFetch("/api/center/auth/me");
    await apiFetch("/api/chat/rooms", { method: "POST", body: "{}" });
    expect(headerOf(fetchMock.mock.calls[0][1], "X-CSRF-Token")).toBeUndefined();
    expect(headerOf(fetchMock.mock.calls[1][1], "X-CSRF-Token")).toBe("csrf-1");
    expect(headerOf(fetchMock.mock.calls[2][1], "X-CSRF-Token")).toBeUndefined();
    expect(headerOf(fetchMock.mock.calls[3][1], "X-CSRF-Token")).toBeUndefined();
  });

  it("falls back to sessionStorage and does not override an explicit header", async () => {
    sessionStorage.setItem("sn_csrf_token", "stored");
    const fetchMock = mockFetch(() => jsonResponse({}));
    await apiFetch("/api/center/x", { method: "DELETE" });
    await apiFetch("/api/center/x", { method: "DELETE", headers: { "X-CSRF-Token": "mine" } });
    expect(headerOf(fetchMock.mock.calls[0][1], "X-CSRF-Token")).toBe("stored");
    expect(headerOf(fetchMock.mock.calls[1][1], "X-CSRF-Token")).toBe("mine");
  });

  it("survives a missing sessionStorage", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    setCsrfToken("a");
    setCsrfToken(null);
    mockFetch(() => jsonResponse({}));
    await expect(apiFetch("/api/center/x", { method: "POST" })).resolves.toEqual({});
    vi.restoreAllMocks();
  });
});

describe("refresh and retry", () => {
  it("refreshes once for parallel 401s and retries each request once", async () => {
    let allowed = false;
    const fetchMock = mockFetch((url) => {
      if (url === REFRESH) {
        allowed = true;
        return jsonResponse({ ...session, csrf_token: "csrf-2" });
      }
      return allowed ? jsonResponse({ ok: url }) : jsonResponse({ detail: "expired" }, 401);
    });
    const results = await Promise.all([apiFetch("/api/chat/a"), apiFetch("/api/photo/b")]);
    expect(results).toEqual([{ ok: "/api/chat/a" }, { ok: "/api/photo/b" }]);
    expect(fetchMock.mock.calls.filter(([url]) => url === REFRESH)).toHaveLength(1);
    await apiFetch("/api/center/z", { method: "POST" });
    expect(headerOf(fetchMock.mock.calls.at(-1)?.[1], "X-CSRF-Token")).toBe("csrf-2");
  });

  it("throws the original 401 when refresh fails and does not loop", async () => {
    const fetchMock = mockFetch((url) =>
      url === REFRESH ? jsonResponse({ detail: "no" }, 401) : jsonResponse({ detail: "expired" }, 401),
    );
    await expect(apiFetch("/api/chat/a")).rejects.toMatchObject({ status: 401, message: "expired" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("retries only once when the retry is also 401", async () => {
    const fetchMock = mockFetch((url) => (url === REFRESH ? jsonResponse(session) : jsonResponse({ detail: "x" }, 401)));
    await expect(apiFetch("/api/chat/a")).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it.each([
    "/api/center/auth/login",
    "/api/center/auth/login/biometric",
    "/api/center/auth/login/voice",
    "/api/center/auth/login/webcam",
    "/api/center/auth/register/combined",
    "/api/center/auth/register",
    "/api/center/auth/google",
    "/api/center/auth/logout",
    "/api/center/auth/me",
    REFRESH,
  ])("does not refresh on a 401 from %s", async (path) => {
    const fetchMock = mockFetch(() => jsonResponse({ detail: "nope" }, 401));
    await expect(apiFetch(path, { method: "POST" })).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("refreshSession reports false on a network error and 204-less success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    expect(await refreshSession()).toBe(false);
    mockFetch(() => new Response("not json", { status: 200 }));
    expect(await refreshSession()).toBe(true);
  });
});

describe("apiForm", () => {
  it("posts multipart without a JSON content type, with CSRF, and retries after refresh", async () => {
    setCsrfToken("csrf-1");
    let first = true;
    const fetchMock = mockFetch((url) => {
      if (url === REFRESH) return jsonResponse(session);
      if (first) {
        first = false;
        return jsonResponse({ detail: "expired" }, 401);
      }
      return jsonResponse({ done: true });
    });
    const form = new FormData();
    form.append("a", "b");
    await expect(apiForm("/api/center/auth/me/biometrics", form)).resolves.toEqual({ done: true });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.body).toBe(form);
    expect(headerOf(init, "Content-Type")).toBeUndefined();
    expect(headerOf(init, "X-CSRF-Token")).toBe("csrf-1");
    expect(fetchMock.mock.calls.at(-1)?.[1].body).toBe(form);
  });

  it("returns undefined on 204 and generic text for unreadable errors", async () => {
    mockFetch(() => jsonResponse(null, 204));
    await expect(apiForm("/api/center/x", new FormData(), { method: "DELETE" })).resolves.toBeUndefined();
    mockFetch(() => new Response("oops", { status: 500 }));
    await expect(apiFetch("/api/chat/x")).rejects.toThrow("Yêu cầu thất bại (500)");
    mockFetch(() => jsonResponse({ detail: [{ msg: "x" }] }, 422));
    await expect(apiFetch("/api/chat/x")).rejects.toThrow("Hãy kiểm tra các ô nhập");
  });
});

describe("loadSession", () => {
  it("returns the user, refreshes once on 401, and returns null when that fails", async () => {
    mockFetch(() => jsonResponse({ id: 1, username: "ann" }));
    expect(await loadSession()).toMatchObject({ username: "ann" });

    let allowed = false;
    mockFetch((url) => {
      if (url === REFRESH) {
        allowed = true;
        return jsonResponse(session);
      }
      return allowed ? jsonResponse({ id: 1, username: "ann" }) : jsonResponse({ detail: "x" }, 401);
    });
    expect(await loadSession()).toMatchObject({ username: "ann" });

    mockFetch(() => jsonResponse({ detail: "x" }, 401));
    expect(await loadSession()).toBeNull();

    mockFetch((url) => (url === REFRESH ? jsonResponse(session) : jsonResponse({ detail: "x" }, 401)));
    expect(await loadSession()).toBeNull();
  });

  it("throws other failures", async () => {
    mockFetch(() => jsonResponse({ detail: "down" }, 503));
    await expect(loadSession()).rejects.toThrow("down");
    let calls = 0;
    mockFetch((url) => {
      if (url === REFRESH) return jsonResponse(session);
      calls += 1;
      return calls === 1 ? jsonResponse({ detail: "x" }, 401) : jsonResponse({ detail: "down" }, 500);
    });
    await expect(loadSession()).rejects.toThrow("down");
  });
});
