import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginFlow from "../../app/center/components/LoginFlow";
import { takeNewUsername } from "../../app/center/lib/auth";
import { jsonResponse, mockFetch, session } from "./helpers";
import { currentTab, selectTab, tabNames } from "./tabs";

const goTo = vi.hoisted(() => vi.fn());
vi.mock("../../app/center/lib/navigate", async (original) => ({
  ...(await original<typeof import("../../app/center/lib/navigate")>()),
  goTo,
}));

const webauthn = vi.hoisted(() => ({ supported: true, start: vi.fn(), create: vi.fn() }));
vi.mock("@simplewebauthn/browser", () => ({
  browserSupportsWebAuthn: () => webauthn.supported,
  startAuthentication: webauthn.start,
  startRegistration: webauthn.create,
}));

// Thiết bị thật cần micro/camera; các bản giả này "ghi" tức thì.
vi.mock("../../app/center/components/AudioRecord", () => ({
  default: ({ onRecorded }: { onRecorded: (b: Blob) => void }) => (
    <button type="button" onClick={() => onRecorded(new Blob(["a"]))}>fake voice</button>
  ),
}));
vi.mock("../../app/center/components/VideoRecord", () => ({
  default: ({ onRecorded }: { onRecorded: (b: Blob) => void }) => (
    <button type="button" onClick={() => onRecorded(new Blob(["v"]))}>fake webcam</button>
  ),
}));
vi.mock("../../app/center/components/BiometricCapture", () => ({
  default: ({ onVideo, onAudio }: { onVideo: (b: Blob) => void; onAudio: (b: Blob) => void }) => (
    <div>
      <button type="button" onClick={() => onVideo(new Blob(["v"]))}>fake video</button>
      <button type="button" onClick={() => onAudio(new Blob(["a"]))}>fake audio</button>
    </div>
  ),
}));
vi.mock("../../app/center/components/GoogleSignInButton", () => ({
  default: ({ onCredential }: { onCredential: (t: string) => void }) => (
    <button type="button" onClick={() => onCredential("idt")}>fake google</button>
  ),
}));

const PLAIN = { google_client_id: null, biometrics_enabled: false };
const BIO = { google_client_id: null, biometrics_enabled: true };
const ALL = { google_client_id: "cid", biometrics_enabled: true };

interface Routes {
  config?: unknown;
  extra?: (url: string, init: RequestInit) => Response | undefined;
}

function setup(routes: Routes = {}) {
  return mockFetch((url, init) => {
    const extra = routes.extra?.(url, init);
    if (extra) return extra;
    if (url.endsWith("/auth/config")) return jsonResponse(routes.config ?? PLAIN);
    if (url.endsWith("/auth/login") || url.endsWith("/auth/google")) return jsonResponse(session);
    if (url.endsWith("/login/voice") || url.endsWith("/login/webcam")) return jsonResponse(session);
    if (url.endsWith("/register/combined")) return jsonResponse(session, 201);
    return jsonResponse({ detail: "unexpected " + url }, 500);
  });
}

type User = ReturnType<typeof userEvent.setup>;

const callTo = (fetchMock: ReturnType<typeof setup>, suffix: string) =>
  fetchMock.mock.calls.find(([url]) => url.endsWith(suffix));
const formOf = (fetchMock: ReturnType<typeof setup>, suffix: string) =>
  callTo(fetchMock, suffix)?.[1].body as FormData;
const calls = (fetchMock: ReturnType<typeof setup>, suffix: string) =>
  fetchMock.mock.calls.filter(([url]) => url.endsWith(suffix));

async function typeName(user: User) {
  // the page checks the session first ("Đang tải..."), so the form is not there on the very first render
  await user.type(await screen.findByLabelText(/^Tên đăng nhập/), "ann");
}
const submit = (user: User, name = "Đăng nhập") => user.click(screen.getByRole("button", { name }));
const openRegister = (user: User) => user.click(screen.getByRole("tab", { name: "Đăng ký" }));
const BAR = "Cách đăng nhập";
/** The bar is built before the config arrives, so wait until it lists what the config should add. */
const waitForTabs = (user: User, check: (names: string[]) => void) =>
  waitFor(async () => check(await tabNames(user, BAR)));

beforeEach(() => {
  webauthn.supported = true;
  webauthn.start.mockReset();
  webauthn.create.mockReset();
  window.sessionStorage.clear();
  goTo.mockReset();
  window.history.pushState({}, "", "/user");
});

describe("LoginFlow selector", () => {
  it("defaults to Mật khẩu, lists every way to sign in and switches on click", async () => {
    setup({ config: ALL });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await waitForTabs(user, (names) =>
      expect(names).toEqual(["Mật khẩu", "Webcam (khuôn mặt)", "Giọng nói", "Mã TOTP", "Mã khôi phục", "Google", "Passkey", "Mã QR"]),
    );
    expect(await currentTab(user, BAR)).toBe("Mật khẩu");
    expect(screen.getByLabelText("Mật khẩu", { selector: "input" })).toBeInTheDocument();

    await selectTab(user, "Giọng nói");
    expect(await currentTab(user, BAR)).toBe("Giọng nói");
    expect(screen.queryByLabelText("Mật khẩu", { selector: "input" })).not.toBeInTheDocument();
    await selectTab(user, "Mã QR");
    expect(await currentTab(user, BAR)).toBe("Mã QR");
  });

  it("hides voice, webcam and Google when they are not configured", async () => {
    setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await screen.findByLabelText("Tên đăng nhập");
    expect(await tabNames(user, BAR)).toEqual(["Mật khẩu", "Mã TOTP", "Mã khôi phục", "Passkey", "Mã QR"]);
  });

  it("shows Google only when a client id is set, voice/webcam only when biometrics are on", async () => {
    setup({ config: { google_client_id: "cid", biometrics_enabled: false } });
    const user = userEvent.setup();
    const first = render(<LoginFlow />);
    await waitForTabs(user, (names) => expect(names).toContain("Google"));
    expect(await tabNames(user, BAR)).not.toContain("Giọng nói");
    first.unmount();
    setup({ config: BIO });
    render(<LoginFlow />);
    await waitForTabs(user, (names) => expect(names).toContain("Webcam (khuôn mặt)"));
    expect(await tabNames(user, BAR)).not.toContain("Google");
  });

  it("keeps working when the config request fails", async () => {
    mockFetch(() => jsonResponse({ detail: "down" }, 503));
    render(<LoginFlow />);
    expect(await screen.findByLabelText("Tên đăng nhập")).toBeInTheDocument();
  });

  it("shows the no-liveness warning only for voice and webcam", async () => {
    setup({ config: BIO });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await selectTab(user, "Giọng nói");
    expect(screen.getByRole("note")).toHaveTextContent(/chưa có kiểm tra người thật/);
    expect(screen.getByRole("note")).toHaveTextContent(/giọng nói/);
    await selectTab(user, "Webcam (khuôn mặt)");
    expect(screen.getByRole("note")).toHaveTextContent(/webcam chưa có kiểm tra người thật/);
    expect(screen.getByRole("note")).not.toHaveTextContent(/giọng/);
    await selectTab(user, "Mật khẩu");
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });
});

describe("LoginFlow password", () => {
  it("signs in with a password and goes home", async () => {
    const fetchMock = setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await typeName(user);
    await user.type(screen.getByLabelText("Mật khẩu", { selector: "input" }), "Password-1x");
    await submit(user);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(JSON.parse(callTo(fetchMock, "/auth/login")?.[1].body as string)).toEqual({
      username: "ann",
      password: "Password-1x",
    });
  });

  it("honors a safe next parameter and ignores an unsafe one", async () => {
    setup();
    window.history.pushState({}, "", "/user?next=%2Fchat");
    const user = userEvent.setup();
    const first = render(<LoginFlow />);
    await typeName(user);
    await user.type(screen.getByLabelText("Mật khẩu", { selector: "input" }), "Password-1x");
    await submit(user);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/chat"));
    first.unmount();

    goTo.mockReset();
    window.history.pushState({}, "", "/user?next=https%3A%2F%2Fevil.com");
    render(<LoginFlow />);
    await typeName(user);
    await user.type(screen.getByLabelText("Mật khẩu", { selector: "input" }), "Password-1x");
    await submit(user);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
  });

  it("shows the server message and stays on the page; 429 gets the throttling text", async () => {
    let status = 401;
    setup({
      extra: (url) =>
        url.endsWith("/auth/login") ? jsonResponse({ detail: "Invalid username or password" }, status) : undefined,
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await typeName(user);
    await user.type(screen.getByLabelText("Mật khẩu", { selector: "input" }), "Password-1x");
    await submit(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");
    expect(goTo).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Đăng nhập" })).toBeEnabled();
    status = 429;
    await user.type(screen.getByLabelText("Mật khẩu", { selector: "input" }), "Password-1x");
    await submit(user);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Thử quá nhiều lần, hãy thử lại sau"));
  });

  it("locks the form while a request is running", async () => {
    let release: (r: Response) => void = () => undefined;
    const fetchMock = mockFetch((url) => {
      if (url.endsWith("/auth/config")) return jsonResponse(PLAIN);
      if (url.endsWith("/auth/me") || url.endsWith("/auth/refresh")) return jsonResponse({ detail: "no" }, 401); // signed out: only the sign-in request hangs
      return new Promise<Response>((resolve) => (release = resolve)) as unknown as Response;
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await typeName(user);
    await user.type(screen.getByLabelText("Mật khẩu", { selector: "input" }), "Password-1x");
    await submit(user);
    expect(await screen.findByRole("button", { name: "Đang xử lý..." })).toBeDisabled();
    await user.type(screen.getByLabelText("Mật khẩu", { selector: "input" }), "{Enter}");
    expect(calls(fetchMock, "/auth/login")).toHaveLength(1);
    release(jsonResponse(session));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
  });
});

describe("LoginFlow voice, webcam and Google sign-in", () => {
  it("signs in with voice: no username input and none sent", async () => {
    const fetchMock = setup({ config: BIO });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await selectTab(user, "Giọng nói");
    expect(screen.queryByLabelText(/Tên đăng nhập/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Mật khẩu", { selector: "input" })).not.toBeInTheDocument();
    expect(screen.getByText("Hệ thống tự nhận ra giọng nói của bạn.")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/chưa có kiểm tra người thật/);
    await submit(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Hãy ghi giọng nói");
    expect(callTo(fetchMock, "/login/voice")).toBeUndefined();
    await user.click(screen.getByRole("button", { name: "fake voice" }));
    await submit(user);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const form = formOf(fetchMock, "/login/voice");
    expect([...form.keys()]).toEqual(["audio"]);
    expect(form.get("audio")).toBeInstanceOf(Blob);
  });

  it("signs in with the webcam: no username input and only the video is sent", async () => {
    const fetchMock = setup({ config: BIO });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await selectTab(user, "Webcam (khuôn mặt)");
    expect(screen.queryByLabelText(/Tên đăng nhập/)).not.toBeInTheDocument();
    expect(screen.getByText("Hệ thống tự nhận ra khuôn mặt của bạn.")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/chưa có kiểm tra người thật/);
    await submit(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Hãy quay khuôn mặt");
    await user.click(screen.getByRole("button", { name: "fake webcam" }));
    await submit(user);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const form = formOf(fetchMock, "/login/webcam");
    expect([...form.keys()]).toEqual(["video"]);
    expect(form.get("video")).toBeInstanceOf(Blob);
  });

  it.each([
    ["Giọng nói", "fake voice", "/login/voice", "audio"],
    ["Webcam (khuôn mặt)", "fake webcam", "/login/webcam", "video"],
  ])("reveals a username input on 422 Enter your username (%s) and resubmits with it", async (tabName, fake, suffix, field) => {
    const fetchMock = setup({
      config: BIO,
      extra: (url, init) => {
        if (!url.endsWith(suffix)) return undefined;
        const hasName = (init.body as FormData).has("username");
        return hasName ? jsonResponse(session) : jsonResponse({ detail: "Enter your username" }, 422);
      },
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await selectTab(user, tabName);
    await user.click(screen.getByRole("button", { name: fake }));
    await submit(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter your username");
    expect(await currentTab(user, BAR)).toBe(tabName);
    const input = screen.getByLabelText("Tên đăng nhập");
    expect(input).toBeRequired();
    expect(screen.getByText(/hãy nhập tên đăng nhập rồi gửi lại/)).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
    await user.type(input, " ann ");
    await user.click(screen.getByRole("button", { name: fake }));
    await submit(user);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const [first, second] = calls(fetchMock, suffix);
    expect((first[1].body as FormData).has("username")).toBe(false);
    const form = second[1].body as FormData;
    expect(form.get("username")).toBe("ann");
    expect(form.get(field)).toBeInstanceOf(Blob);
  });

  it("hides the fallback username input again when the tab changes", async () => {
    setup({
      config: BIO,
      extra: (url) => (url.endsWith("/login/voice") ? jsonResponse({ detail: "Enter your username" }, 422) : undefined),
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await selectTab(user, "Giọng nói");
    await user.click(screen.getByRole("button", { name: "fake voice" }));
    await submit(user);
    await screen.findByLabelText("Tên đăng nhập");
    await selectTab(user, "Webcam (khuôn mặt)");
    expect(screen.queryByLabelText(/Tên đăng nhập/)).not.toBeInTheDocument();
  });

  it("keeps the username required on the password tab", async () => {
    setup({ config: BIO });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await waitForTabs(user, (names) => expect(names).toContain("Giọng nói"));
    expect(screen.getByLabelText("Tên đăng nhập")).toBeRequired();
  });

  it.each([
    [409, "This face is already registered"],
    [429, "Thử quá nhiều lần, hãy thử lại sau"],
    [401, "Biometric login failed"],
  ])("shows the error for webcam sign-in %i", async (status, text) => {
    setup({
      config: BIO,
      extra: (url) => (url.endsWith("/login/webcam") ? jsonResponse({ detail: text }, status) : undefined),
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await selectTab(user, "Webcam (khuôn mặt)");
    await user.click(screen.getByRole("button", { name: "fake webcam" }));
    await submit(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(goTo).not.toHaveBeenCalled();
  });

  it("shows the server error when a biometric sign-in fails and clears the recording", async () => {
    const fetchMock = setup({
      config: BIO,
      extra: (url) => (url.endsWith("/login/voice") ? jsonResponse({ detail: "Biometric login failed" }, 401) : undefined),
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await selectTab(user, "Giọng nói");
    await user.click(screen.getByRole("button", { name: "fake voice" }));
    await submit(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Biometric login failed");
    expect(goTo).not.toHaveBeenCalled();
    await submit(user); // recording was cleared after the attempt
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Hãy ghi giọng nói"));
    expect(calls(fetchMock, "/login/voice")).toHaveLength(1);
  });

  it("clears recordings when the method is switched", async () => {
    const fetchMock = setup({ config: BIO });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await selectTab(user, "Giọng nói");
    await user.click(screen.getByRole("button", { name: "fake voice" }));
    await selectTab(user, "Webcam (khuôn mặt)");
    await selectTab(user, "Giọng nói");
    await submit(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Hãy ghi giọng nói");
    expect(callTo(fetchMock, "/login/voice")).toBeUndefined();
  });

  it("signs in with Google from the Google tab", async () => {
    const fetchMock = setup({ config: ALL });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await selectTab(user, "Google");
    expect(screen.queryByLabelText("Tên đăng nhập")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "fake google" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(JSON.parse(callTo(fetchMock, "/auth/google")?.[1].body as string)).toEqual({ id_token: "idt" });
  });
});

describe("LoginFlow second factor (unchanged)", () => {
  const mfa = (url: string) =>
    url.endsWith("/auth/login") || url.endsWith("/auth/google")
      ? jsonResponse({ mfa_required: true, mfa_token: "tok" })
      : undefined;

  async function reachMfa(user: User) {
    await typeName(user);
    await user.type(screen.getByLabelText("Mật khẩu", { selector: "input" }), "Password-1x");
    await submit(user);
    await screen.findByRole("heading", { name: "Xác minh danh tính" });
  }

  it("asks for the second factor after the password and finishes with the clip", async () => {
    const fetchMock = setup({
      extra: (url) => mfa(url) ?? (url.endsWith("/auth/login/biometric") ? jsonResponse(session) : undefined),
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    expect(goTo).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Xác minh và đăng nhập" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "fake video" }));
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const body = formOf(fetchMock, "/auth/login/biometric");
    expect(body.get("mfa_token")).toBe("tok");
    expect(body.get("video")).toBeInstanceOf(File);
  });

  it("also applies to Google sign-in", async () => {
    setup({ config: ALL, extra: mfa });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await selectTab(user, "Google");
    await user.click(screen.getByRole("button", { name: "fake google" }));
    expect(await screen.findByRole("heading", { name: "Xác minh danh tính" })).toBeInTheDocument();
  });

  it("returns to the sign-in form when cancelled", async () => {
    setup({ extra: mfa });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    await user.click(screen.getByRole("button", { name: "Hủy" }));
    expect(await screen.findByRole("tab", { name: "Đăng nhập", selected: true })).toBeInTheDocument();
    expect(screen.getByLabelText("Mật khẩu", { selector: "input" })).toHaveValue("");
  });

  it("shows the server message when the second factor does not match", async () => {
    setup({
      extra: (url) =>
        mfa(url) ??
        (url.endsWith("/auth/login/biometric") ? jsonResponse({ detail: "Biometric verification failed" }, 401) : undefined),
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    await user.click(screen.getByRole("button", { name: "fake audio" }));
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Biometric verification failed");
    expect(goTo).not.toHaveBeenCalled();
  });
});

describe("LoginFlow voice/webcam with a TOTP account", () => {
  it.each([
    ["Giọng nói", "fake voice", "/login/voice"],
    ["Webcam (khuôn mặt)", "fake webcam", "/login/webcam"],
  ])("%s sign-in leads to the authenticator step", async (tab, fake, route) => {
    setup({
      config: BIO,
      extra: (url) => (url.endsWith(route) ? jsonResponse({ mfa_required: true, mfa_token: "tok", factors: ["totp"] }) : undefined),
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await selectTab(user, tab);
    await user.click(screen.getByRole("button", { name: fake }));
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
    expect(await screen.findByRole("heading", { name: "Xác minh danh tính" })).toBeInTheDocument();
    expect(screen.getByLabelText("Mã xác thực 6 chữ số")).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });
});

describe("LoginFlow register (no checkboxes)", () => {
  async function register(config: unknown = PLAIN) {
    const fetchMock = setup({ config });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await screen.findByLabelText("Tên đăng nhập");
    await openRegister(user);
    return { fetchMock, user };
  }
  // A method counts as soon as its tab holds something; there is nothing to tick.
  const openTab = (user: User, method: string) => selectTab(user, method);
  const passwordInput = () => screen.getByLabelText("Mật khẩu", { selector: "input[type=password]" });
  const field = () => screen.getByLabelText(/^Tên đăng nhập/);
  const summary = () => screen.getByText(/Sẽ đăng ký bằng|Điền một tab/);

  it("starts with no method chosen and no username required", async () => {
    await register(ALL);
    expect(screen.getByRole("tab", { name: "Đăng ký", selected: true })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Đăng ký" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(field()).not.toBeRequired();
    expect(screen.getByLabelText("Tên đăng nhập (không bắt buộc)")).toBeInTheDocument();
    expect(summary()).toHaveTextContent(/Điền một tab/);
  });

  it("hides unconfigured methods and the tabs registration cannot use", async () => {
    const { user } = await register();
    expect(await tabNames(user, "Cách đăng ký")).toEqual(["Mật khẩu", "Passkey"]);
  });

  it("requires the username only once a password is typed", async () => {
    const { user } = await register(ALL);
    expect(field()).not.toBeRequired();
    await user.type(passwordInput(), "x");
    expect(field()).toBeRequired();
    expect(field()).toHaveAttribute("aria-required", "true");
    expect(summary()).toHaveTextContent("Sẽ đăng ký bằng: Mật khẩu");
    await user.clear(passwordInput());
    expect(field()).not.toBeRequired();
    expect(screen.getByText(/Không bắt buộc nếu chỉ dùng Google, Giọng nói, Webcam hoặc Passkey/)).toBeInTheDocument();
  });

  it("registers with voice only, omits a blank username and keeps the notice", async () => {
    const generated = { ...session, username: "user-9b1c3d" };
    const { fetchMock, user } = await register(BIO);
    fetchMock.mockImplementation(async () => jsonResponse(generated, 201));
    await openTab(user, "Giọng nói");
    await user.click(screen.getByRole("button", { name: "fake voice" }));
    expect(summary()).toHaveTextContent("Sẽ đăng ký bằng: Giọng nói");
    await submit(user, "Đăng ký");
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect([...formOf(fetchMock, "/register/combined").keys()]).toEqual(["voice_audio"]);
    expect(takeNewUsername()).toBe("user-9b1c3d");
  });

  it("registers with the webcam only, omits a blank username and keeps the notice once", async () => {
    const generated = { ...session, username: "user-7f3a2c" };
    const { fetchMock, user } = await register(BIO);
    fetchMock.mockImplementation(async () => jsonResponse(generated, 201));
    await openTab(user, "Webcam (khuôn mặt)");
    await user.click(screen.getByRole("button", { name: "fake webcam" }));
    await submit(user, "Đăng ký");
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect([...formOf(fetchMock, "/register/combined").keys()]).toEqual(["webcam_video"]);
    expect(formOf(fetchMock, "/register/combined").has("audio")).toBe(false);
    expect(takeNewUsername()).toBe("user-7f3a2c");
    expect(takeNewUsername()).toBeNull();
  });

  it("does not keep a notice when the user typed the username", async () => {
    const { user } = await register(BIO);
    await openTab(user, "Webcam (khuôn mặt)");
    await user.click(screen.getByRole("button", { name: "fake webcam" }));
    await user.type(screen.getByLabelText("Tên đăng nhập (không bắt buộc)"), "ann");
    await submit(user, "Đăng ký");
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(takeNewUsername()).toBeNull();
  });

  it("blocks a blank username when a password is typed", async () => {
    const { fetchMock, user } = await register();
    await user.type(passwordInput(), "Password-1x");
    await user.type(field(), "   ");
    await submit(user, "Đăng ký");
    expect(await screen.findByRole("alert")).toHaveTextContent("Hãy nhập tên đăng nhập");
    expect(callTo(fetchMock, "/register/combined")).toBeUndefined();
  });

  it("registers with a password only via the combined route", async () => {
    const { fetchMock, user } = await register();
    await typeName(user);
    await user.type(passwordInput(), "Password-1x");
    await submit(user, "Đăng ký");
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const form = formOf(fetchMock, "/register/combined");
    expect([...form.keys()].sort()).toEqual(["password", "username"]);
    expect(form.get("username")).toBe("ann");
    expect(form.get("password")).toBe("Password-1x");
  });

  it("shows live password hints and blocks short passwords locally", async () => {
    const { fetchMock, user } = await register();
    await typeName(user);
    expect(screen.getByText(/Cần 8 ký tự trở lên và đủ 4 loại ký tự/)).toBeInTheDocument();
    await user.type(passwordInput(), "short");
    await submit(user, "Đăng ký");
    expect(await screen.findByRole("alert")).toHaveTextContent("Mật khẩu cần 8-128 ký tự");
    expect(callTo(fetchMock, "/register/combined")).toBeUndefined();
    await user.type(passwordInput(), "12345");
    expect(screen.getByText(/Chữ hoa \(A-Z\): chưa có/)).toBeInTheDocument();
    expect(screen.getByText(/Chữ số \(0-9\): đã có/)).toBeInTheDocument();
  });

  it("registers with password + voice and shows the warning", async () => {
    const { fetchMock, user } = await register(BIO);
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    await typeName(user);
    await user.type(passwordInput(), "Password-1x");
    await openTab(user, "Giọng nói");
    expect(screen.getByRole("note")).toHaveTextContent(/chưa có kiểm tra người thật/);
    await user.click(screen.getByRole("button", { name: "fake voice" }));
    expect(summary()).toHaveTextContent("Sẽ đăng ký bằng: Mật khẩu, Giọng nói");
    await submit(user, "Đăng ký");
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const form = formOf(fetchMock, "/register/combined");
    expect([...form.keys()].sort()).toEqual(["password", "username", "voice_audio"]);
  });

  it("registers with voice + webcam and no password", async () => {
    const { fetchMock, user } = await register(BIO);
    await openTab(user, "Giọng nói");
    await user.click(screen.getByRole("button", { name: "fake voice" }));
    await openTab(user, "Webcam (khuôn mặt)");
    await user.click(screen.getByRole("button", { name: "fake webcam" }));
    await user.type(field(), "ann");
    await submit(user, "Đăng ký");
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const form = formOf(fetchMock, "/register/combined");
    expect([...form.keys()].sort()).toEqual(["username", "voice_audio", "webcam_video"]);
    expect(form.get("webcam_video")).toBeInstanceOf(Blob);
  });

  it("keeps a recording while another tab is open", async () => {
    const { fetchMock, user } = await register(BIO);
    await openTab(user, "Webcam (khuôn mặt)");
    await user.click(screen.getByRole("button", { name: "fake webcam" }));
    await openTab(user, "Mật khẩu");
    await openTab(user, "Giọng nói");
    expect(summary()).toHaveTextContent("Sẽ đăng ký bằng: Webcam (khuôn mặt)");
    await submit(user, "Đăng ký");
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(formOf(fetchMock, "/register/combined").get("webcam_video")).toBeInstanceOf(Blob);
  });

  it("drops a recording with the button and then needs another method", async () => {
    const { fetchMock, user } = await register(BIO);
    await openTab(user, "Webcam (khuôn mặt)");
    await user.click(screen.getByRole("button", { name: "fake webcam" }));
    await user.click(screen.getByRole("button", { name: "Không dùng cách này" }));
    expect(summary()).toHaveTextContent(/Điền một tab/);
    await submit(user, "Đăng ký");
    expect(await screen.findByRole("alert")).toHaveTextContent("Hãy điền ít nhất một cách đăng ký");
    expect(callTo(fetchMock, "/register/combined")).toBeUndefined();
  });

  it("keeps the Google credential in a chip, does not submit, and can clear it", async () => {
    const { fetchMock, user } = await register(ALL);
    await openTab(user, "Google");
    expect(screen.getByText("Chọn tài khoản Google")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "fake google" }));
    expect(screen.getByText(/Đã chọn tài khoản Google/)).toBeInTheDocument();
    // picking a Google account does not submit: only the page's own config and session checks went out
    expect(fetchMock.mock.calls.filter(([url]) => !url.endsWith("/auth/config") && !url.endsWith("/auth/me"))).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Chọn lại" }));
    expect(screen.getByRole("button", { name: "fake google" })).toBeInTheDocument();
  });

  it("registers with Google + password", async () => {
    const { fetchMock, user } = await register(ALL);
    await typeName(user);
    await user.type(passwordInput(), "Password-1x");
    await openTab(user, "Google");
    await user.click(screen.getByRole("button", { name: "fake google" }));
    await submit(user, "Đăng ký");
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const form = formOf(fetchMock, "/register/combined");
    expect([...form.keys()].sort()).toEqual(["google_id_token", "password", "username"]);
    expect(form.get("google_id_token")).toBe("idt");
  });

  it("requires at least one method", async () => {
    const { fetchMock, user } = await register();
    await typeName(user);
    await submit(user, "Đăng ký");
    expect(await screen.findByRole("alert")).toHaveTextContent("Hãy điền ít nhất một cách đăng ký");
    expect(callTo(fetchMock, "/register/combined")).toBeUndefined();
  });

  it.each([
    [409, "Username already taken"],
    [409, "This face is already registered"],
    [409, "This voice is already registered"],
    [422, "Choose a username"],
    [422, "Enter your username"],
    [400, "Voice or face sample is unusable, record again"],
    [401, "Invalid Google token"],
    [503, "Biometrics are not available"],
  ])("shows the server detail for %i and lets the user retry", async (status, detail) => {
    let fail = true;
    const { fetchMock, user } = await register();
    fetchMock.mockImplementation(async (url) =>
      url.endsWith("/register/combined") && fail ? jsonResponse({ detail }, status) : jsonResponse(session, 201),
    );
    await typeName(user);
    await user.type(screen.getByLabelText("Mật khẩu", { selector: "input[type=password]" }), "Password-1x");
    await submit(user, "Đăng ký");
    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
    if (detail.includes("voice")) expect(screen.getByRole("alert")).toHaveTextContent("Giọng nói này đã được đăng ký");
    expect(goTo).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Tên đăng nhập")).toHaveValue("ann");
    expect(screen.getByLabelText("Mật khẩu", { selector: "input[type=password]" })).toHaveValue("Password-1x");
    fail = false;
    await submit(user, "Đăng ký");
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
  });

  it("shows the throttling text on 429", async () => {
    const { fetchMock, user } = await register();
    fetchMock.mockImplementation(async () => jsonResponse({ detail: "slow" }, 429));
    await typeName(user);
    await user.type(screen.getByLabelText("Mật khẩu", { selector: "input[type=password]" }), "Password-1x");
    await submit(user, "Đăng ký");
    expect(await screen.findByRole("alert")).toHaveTextContent("Thử quá nhiều lần, hãy thử lại sau");
  });

  it("switches back to login with the single-method selector", async () => {
    const { user } = await register(ALL);
    await user.click(screen.getByRole("tab", { name: "Đăng nhập" }));
    expect(screen.getByRole("tab", { name: "Đăng nhập", selected: true })).toBeInTheDocument();
    expect(screen.getByRole("tablist")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("offers the Google picker once the Google tab is open", async () => {
    const { user } = await register({ google_client_id: "cid", biometrics_enabled: false });
    await openTab(user, "Google");
    expect(screen.getByRole("button", { name: "fake google" })).toBeInTheDocument();
  });
});
