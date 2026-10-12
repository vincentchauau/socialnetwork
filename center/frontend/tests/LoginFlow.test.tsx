import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginFlow from "../app/components/LoginFlow";
import { jsonResponse, mockFetch, session } from "./helpers";

const goTo = vi.hoisted(() => vi.fn());
vi.mock("../app/lib/navigate", async (original) => ({
  ...(await original<typeof import("../app/lib/navigate")>()),
  goTo,
}));

// Thiết bị thật cần camera; bản giả này "quay" tức thì.
vi.mock("../app/components/BiometricCapture", () => ({
  default: ({ onVideo, onAudio }: { onVideo: (b: Blob) => void; onAudio: (b: Blob) => void }) => (
    <div>
      <button type="button" onClick={() => onVideo(new Blob(["v"]))}>
        fake video
      </button>
      <button type="button" onClick={() => onAudio(new Blob(["a"]))}>
        fake audio
      </button>
    </div>
  ),
}));

const CONFIG = { google_client_id: null, biometrics_enabled: false };
const BIO = { google_client_id: null, biometrics_enabled: true };

interface Routes {
  config?: unknown;
  login?: () => Response;
  extra?: (url: string, init: RequestInit) => Response | undefined;
}

function setup(routes: Routes = {}) {
  return mockFetch((url, init) => {
    const extra = routes.extra?.(url, init);
    if (extra) return extra;
    if (url.endsWith("/auth/config")) return jsonResponse(routes.config ?? CONFIG);
    if (url.endsWith("/auth/login")) return routes.login?.() ?? jsonResponse(session);
    if (url.endsWith("/auth/register")) return jsonResponse(session, 201);
    return jsonResponse({ detail: "unexpected " + url }, 500);
  });
}

type User = ReturnType<typeof userEvent.setup>;

async function fill(user: User, password = "password1") {
  await user.type(screen.getByLabelText("Tên đăng nhập"), "ann");
  if (password) await user.type(screen.getByLabelText("Mật khẩu"), password);
}

async function fillAndSubmit(user: User, password = "password1", button = "Đăng nhập") {
  await fill(user, password);
  await user.click(screen.getByRole("button", { name: button }));
}

const callTo = (fetchMock: ReturnType<typeof setup>, suffix: string) =>
  fetchMock.mock.calls.find(([url]) => url.endsWith(suffix));

beforeEach(() => {
  goTo.mockReset();
  window.history.pushState({}, "", "/login");
});

describe("LoginFlow password", () => {
  it("signs in with a password and goes home", async () => {
    const fetchMock = setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await fillAndSubmit(user);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(JSON.parse(callTo(fetchMock, "/auth/login")?.[1].body as string)).toEqual({
      username: "ann",
      password: "password1",
    });
  });

  it("honors a safe next parameter and ignores an unsafe one", async () => {
    setup();
    window.history.pushState({}, "", "/login?next=%2Fchat");
    const user = userEvent.setup();
    const first = render(<LoginFlow />);
    await fillAndSubmit(user);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/chat"));
    first.unmount();

    goTo.mockReset();
    window.history.pushState({}, "", "/login?next=https%3A%2F%2Fevil.com");
    render(<LoginFlow />);
    await fillAndSubmit(user);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
  });

  it("shows the server message for a wrong password and stays on the page", async () => {
    setup({ login: () => jsonResponse({ detail: "Invalid username or password" }, 401) });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await fillAndSubmit(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");
    expect(goTo).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Đăng nhập" })).toBeEnabled();
  });

  it("shows a throttling message on 429", async () => {
    setup({ login: () => jsonResponse({ detail: "slow down" }, 429) });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await fillAndSubmit(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Thử quá nhiều lần, hãy thử lại sau");
  });

  it("locks the form while a request is running", async () => {
    let release: (r: Response) => void = () => undefined;
    const fetchMock = mockFetch((url) => {
      if (url.endsWith("/auth/config")) return jsonResponse(CONFIG);
      return new Promise<Response>((resolve) => (release = resolve)) as unknown as Response;
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await fillAndSubmit(user);
    expect(await screen.findByRole("button", { name: "Đang xử lý..." })).toBeDisabled();
    await user.type(screen.getByLabelText("Mật khẩu"), "{Enter}");
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith("/auth/login"))).toHaveLength(1);
    release(jsonResponse(session));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
  });
});

describe("LoginFlow register and mode switch", () => {
  it("blocks short passwords locally, then registers", async () => {
    const fetchMock = setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await user.click(screen.getByRole("button", { name: "Chưa có tài khoản? Đăng ký" }));
    expect(screen.getByRole("heading", { name: "Đăng ký" })).toBeInTheDocument();
    await fillAndSubmit(user, "short", "Đăng ký");
    expect(await screen.findByRole("alert")).toHaveTextContent("Mật khẩu cần ít nhất 8 ký tự");
    expect(callTo(fetchMock, "/register")).toBeUndefined();
    await user.type(screen.getByLabelText("Mật khẩu"), "12345");
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(callTo(fetchMock, "/me/biometrics")).toBeUndefined();
  });

  it("switches back to login", async () => {
    setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await user.click(screen.getByRole("button", { name: "Chưa có tài khoản? Đăng ký" }));
    await user.click(screen.getByRole("button", { name: "Đã có tài khoản? Đăng nhập" }));
    expect(screen.getByRole("heading", { name: "Đăng nhập" })).toBeInTheDocument();
  });

  it("enrolls the recording made at register time with the new csrf token", async () => {
    const fetchMock = setup({ config: BIO });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await user.click(await screen.findByRole("button", { name: "fake video" }));
    await user.click(screen.getByRole("button", { name: "Chưa có tài khoản? Đăng ký" }));
    await user.click(screen.getByRole("button", { name: "fake video" }));
    await fillAndSubmit(user, "password1", "Đăng ký");
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const enroll = callTo(fetchMock, "/me/biometrics");
    expect((enroll?.[1].body as FormData).get("password")).toBe("password1");
    expect((enroll?.[1].body as FormData).get("video")).toBeInstanceOf(Blob);
    expect((enroll?.[1].headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-1");
  });

  it("still finishes registering when the enrolment fails", async () => {
    setup({
      config: BIO,
      extra: (url) => (url.endsWith("/me/biometrics") ? jsonResponse({ detail: "no face" }, 400) : undefined),
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await user.click(await screen.findByRole("button", { name: "Chưa có tài khoản? Đăng ký" }));
    await user.click(screen.getByRole("button", { name: "fake audio" }));
    await fillAndSubmit(user, "password1", "Đăng ký");
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
  });
});

describe("LoginFlow optional features", () => {
  it("hides recorders and Google without config", async () => {
    setup();
    render(<LoginFlow />);
    await screen.findByLabelText("Tên đăng nhập");
    expect(screen.queryByLabelText("Đăng nhập bằng Google")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "fake video" })).not.toBeInTheDocument();
  });

  it("shows the recorders when biometrics are enabled", async () => {
    setup({ config: BIO });
    render(<LoginFlow />);
    expect(await screen.findByRole("button", { name: "fake video" })).toBeInTheDocument();
  });

  it("shows a graceful error when the Google script cannot load", async () => {
    setup({ config: { google_client_id: "cid", biometrics_enabled: false } });
    const appendSpy = vi.spyOn(document.head, "appendChild").mockImplementation((node) => {
      queueMicrotask(() => (node as HTMLScriptElement).onerror?.(new Event("error")));
      return node;
    });
    render(<LoginFlow />);
    expect(await screen.findByText(/Không tải được đăng nhập Google/)).toBeInTheDocument();
    expect(appendSpy).toHaveBeenCalled();
    appendSpy.mockRestore();
  });

  it("keeps working when the config request fails", async () => {
    mockFetch(() => jsonResponse({ detail: "down" }, 503));
    render(<LoginFlow />);
    expect(await screen.findByLabelText("Tên đăng nhập")).toBeInTheDocument();
  });
});

describe("LoginFlow biometrics", () => {
  it("sends the recording straight to the second step after the password", async () => {
    const fetchMock = setup({
      config: BIO,
      login: () => jsonResponse({ mfa_required: true, mfa_token: "mfa-1" }),
      extra: (url) => (url.endsWith("/login/biometric") ? jsonResponse(session) : undefined),
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await user.click(await screen.findByRole("button", { name: "fake video" }));
    await fillAndSubmit(user);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const form = callTo(fetchMock, "/login/biometric")?.[1].body as FormData;
    expect(form.get("mfa_token")).toBe("mfa-1");
    expect(form.get("video")).toBeInstanceOf(Blob);
  });

  it("asks for a recording in the same card when none was made, and can cancel", async () => {
    const fetchMock = setup({
      config: BIO,
      login: () => jsonResponse({ mfa_required: true, mfa_token: "mfa-1" }),
      extra: (url) => (url.endsWith("/login/biometric") ? jsonResponse(session) : undefined),
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await fillAndSubmit(user);
    expect(await screen.findByRole("heading", { name: "Xác minh danh tính" })).toBeInTheDocument();
    const verify = screen.getByRole("button", { name: "Xác minh và đăng nhập" });
    expect(verify).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Hủy" }));
    expect(await screen.findByRole("heading", { name: "Đăng nhập" })).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();

    await fillAndSubmit(user);
    await user.click(await screen.findByRole("button", { name: "fake audio" }));
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect((callTo(fetchMock, "/login/biometric")?.[1].body as FormData).get("audio")).toBeInstanceOf(Blob);
  });

  it("shows server errors from the second step", async () => {
    setup({
      config: BIO,
      login: () => jsonResponse({ mfa_required: true, mfa_token: "m" }),
      extra: (url) => (url.endsWith("/login/biometric") ? jsonResponse({ detail: "Face did not match" }, 401) : undefined),
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await fillAndSubmit(user);
    await user.click(await screen.findByRole("button", { name: "fake video" }));
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    expect(await screen.findByText("Face did not match")).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });

  it("signs in with face + voice only when the password is empty", async () => {
    const fetchMock = setup({
      config: BIO,
      extra: (url) => (url.endsWith("/biometric-only") ? jsonResponse(session) : undefined),
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await user.click(await screen.findByRole("button", { name: "fake video" }));
    await user.click(screen.getByRole("button", { name: "fake audio" }));
    await fillAndSubmit(user, "");
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const form = callTo(fetchMock, "/biometric-only")?.[1].body as FormData;
    expect(form.get("username")).toBe("ann");
    expect(form.get("audio")).toBeInstanceOf(Blob);
    expect(callTo(fetchMock, "/auth/login")).toBeUndefined();
  });

  it("clears recordings on mode switch so they are not reused", async () => {
    const fetchMock = setup({ config: BIO, login: () => jsonResponse({ mfa_required: true, mfa_token: "m" }) });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await user.click(await screen.findByRole("button", { name: "fake video" }));
    await user.click(screen.getByRole("button", { name: "Chưa có tài khoản? Đăng ký" }));
    await user.click(screen.getByRole("button", { name: "Đã có tài khoản? Đăng nhập" }));
    await fillAndSubmit(user);
    expect(await screen.findByRole("heading", { name: "Xác minh danh tính" })).toBeInTheDocument();
    expect(callTo(fetchMock, "/login/biometric")).toBeUndefined();
  });
});
