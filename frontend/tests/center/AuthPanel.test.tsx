import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginFlow from "../../app/center/components/LoginFlow";
import { jsonResponse, me, mockFetch, session } from "./helpers";
import { currentTab, selectTab, tabNames } from "./tabs";

const goTo = vi.hoisted(() => vi.fn());
vi.mock("../../app/center/lib/navigate", async (original) => ({
  ...(await original<typeof import("../../app/center/lib/navigate")>()),
  goTo,
}));

vi.mock("@simplewebauthn/browser", () => ({
  browserSupportsWebAuthn: () => true,
  startAuthentication: vi.fn(),
  startRegistration: vi.fn(),
}));
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
vi.mock("../../app/center/components/GoogleSignInButton", () => ({
  default: ({ onCredential }: { onCredential: (t: string) => void }) => (
    <button type="button" onClick={() => onCredential("idt")}>fake google</button>
  ),
}));

const EVERYTHING = { google_client_id: "cid", biometrics_enabled: true, email_enabled: true, phone_enabled: true };
const PLAIN = { google_client_id: null, biometrics_enabled: false };
const MFA_TOTP = { mfa_required: true, mfa_token: "tok", factors: ["totp"] };

type User = ReturnType<typeof userEvent.setup>;
type Handler = (url: string, init: RequestInit) => Response | undefined;

function setup(config: unknown = PLAIN, extra?: Handler) {
  return mockFetch((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/config")) return jsonResponse(config);
    if (url.endsWith("/auth/login") || url.endsWith("/auth/login/totp")) return jsonResponse(session);
    return jsonResponse({ detail: "unexpected " + url }, 500);
  });
}

const callsTo = (fn: ReturnType<typeof setup>, suffix: string) => fn.mock.calls.filter(([url]) => url.endsWith(suffix));
const link = (name: string) => screen.getByRole("link", { name });
const passwordInput = () => screen.getByLabelText("Mật khẩu", { selector: "input[type=password]" });
const signInButton = () => screen.getByRole("button", { name: "Đăng nhập" });

async function fillPassword(user: User) {
  await selectTab(user, "Mật khẩu");
  await user.type(screen.getByLabelText("Tên đăng nhập"), "ann");
  await user.type(passwordInput(), "Password-1x");
}

async function open() {
  const user = userEvent.setup();
  render(<LoginFlow />);
  await screen.findByLabelText("Tên đăng nhập");
  return user;
}

beforeEach(() => {
  goTo.mockReset();
  window.sessionStorage.clear();
  window.history.pushState({}, "", "/user");
});

describe("AuthPanel modes", () => {
  it("offers sign-in and register, and no link to change the account while signed out", async () => {
    const fn = setup(PLAIN, (url) => (url.endsWith("/auth/me") ? jsonResponse({ detail: "no" }, 401) : undefined));
    await open();
    expect(screen.getByRole("tab", { name: "Đăng nhập" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Đăng ký" })).toHaveAttribute("aria-selected", "false");
    await waitFor(() => expect(callsTo(fn, "/auth/me").length).toBeGreaterThan(0)); // the session check has finished
    expect(screen.queryByRole("tab", { name: "Cập nhật" })).not.toBeInTheDocument();
  });

  it("opens a signed-in visitor of /login on Cập nhật, the only mode of a signed-in person", async () => {
    setup(PLAIN, (url) => (url.endsWith("/auth/me") ? jsonResponse(me) : url.endsWith("/auth/sessions") ? jsonResponse([]) : undefined));
    render(<LoginFlow />);
    expect(await screen.findByRole("form", { name: "Đổi mật khẩu" })).toBeInTheDocument();
    const modes = screen.getByRole("tablist", { name: "Chế độ" });
    expect(within(modes).getAllByRole("tab").map((mode) => mode.textContent)).toEqual(["Cập nhật"]);
    expect(within(modes).getByRole("tab", { name: "Cập nhật" })).toHaveAttribute("aria-selected", "true");
    expect(goTo).not.toHaveBeenCalled(); // /login does not send a signed-in visitor anywhere: this is where Cập nhật is
  });

  it("groups the tabs and lists every method when sign-in has all of them", async () => {
    setup(EVERYTHING);
    const user = await open();
    // the bar is built before the config arrives: wait until it has every tab
    await waitFor(async () =>
      expect(await tabNames(user, "Cách đăng nhập")).toEqual([
        "Mật khẩu", "Webcam (khuôn mặt)", "Giọng nói", "Mã TOTP", "Mã khôi phục", "Email", "SMS", "Google", "Passkey", "Mã QR",
      ]),
    );
  });

  it("offers registration only the methods it can use", async () => {
    setup(EVERYTHING);
    const user = await open();
    await user.click(screen.getByRole("tab", { name: "Đăng ký" }));
    expect(await tabNames(user, "Cách đăng ký")).toEqual(["Mật khẩu", "Webcam (khuôn mặt)", "Giọng nói", "Email", "Google", "Passkey"]);
  });

  it("keeps the open tab when the new mode has it, else falls back to Mật khẩu", async () => {
    setup(EVERYTHING);
    const user = await open();
    await selectTab(user, "Passkey");
    await user.click(screen.getByRole("tab", { name: "Đăng ký" }));
    expect(await currentTab(user, "Cách đăng ký")).toBe("Passkey"); // registration offers Passkey too
    await user.click(screen.getByRole("tab", { name: "Đăng nhập" }));
    await selectTab(user, "Mã TOTP");
    await user.click(screen.getByRole("tab", { name: "Đăng ký" }));
    expect(await currentTab(user, "Cách đăng ký")).toBe("Mật khẩu"); // no TOTP in registration
  });
});

describe("AuthPanel sign-in button", () => {
  it("signs in with the password tab", async () => {
    const fn = setup();
    const user = await open();
    await fillPassword(user);
    await user.click(signInButton());
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(callsTo(fn, "/auth/login")).toHaveLength(1);
  });

  it("signs in when Enter is pressed in a field", async () => {
    const fn = setup();
    const user = await open();
    await user.type(screen.getByLabelText("Tên đăng nhập"), "ann");
    await user.type(passwordInput(), "Password-1x{Enter}");
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(callsTo(fn, "/auth/login")).toHaveLength(1);
  });

  it("asks for the password when the code tab is open and the password is missing", async () => {
    const fn = setup();
    const user = await open();
    await selectTab(user, "Mã TOTP");
    await user.type(screen.getByLabelText("Mã xác thực 6 chữ số"), "123456");
    await user.click(signInButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Hãy nhập tên đăng nhập và mật khẩu ở tab Mật khẩu");
    expect(callsTo(fn, "/auth/login")).toHaveLength(0);
  });

  it("hides the bottom button on a tab that has its own action", async () => {
    setup({ ...PLAIN, email_enabled: true });
    const user = await open();
    await selectTab(user, "Email");
    expect(screen.queryByRole("button", { name: "Đăng nhập" })).not.toBeInTheDocument();
    expect(screen.getByText("Hoàn tất bằng nút ngay trong tab này.")).toBeInTheDocument();
  });

  it("drops a recording when another tab opens", async () => {
    setup({ google_client_id: null, biometrics_enabled: true });
    const user = await open();
    await selectTab(user, "Giọng nói");
    await user.click(screen.getByRole("button", { name: "fake voice" }));
    await selectTab(user, "Webcam (khuôn mặt)");
    await selectTab(user, "Giọng nói");
    await user.click(signInButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Hãy ghi giọng nói");
  });
});

describe("AuthPanel second step", () => {
  const withMfa: Handler = (url) => (url.endsWith("/auth/login") ? jsonResponse(MFA_TOTP) : undefined);

  it("sends the TOTP code from its tab at step two in one go", async () => {
    const fn = setup(PLAIN, withMfa);
    const user = await open();
    await selectTab(user, "Mã TOTP");
    await user.type(screen.getByLabelText("Mã xác thực 6 chữ số"), "123456");
    await fillPassword(user);
    await user.click(signInButton());
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const totp = callsTo(fn, "/auth/login/totp");
    expect(totp).toHaveLength(1);
    expect(JSON.parse(String(totp[0][1].body))).toEqual({ mfa_token: "tok", code: "123456" });
    expect(screen.queryByRole("heading", { name: "Xác minh danh tính" })).not.toBeInTheDocument();
  });

  it("sends a recovery code, trimmed and lowercased, in preference to the TOTP code", async () => {
    const fn = setup(PLAIN, withMfa);
    const user = await open();
    await selectTab(user, "Mã TOTP");
    await user.type(screen.getByLabelText("Mã xác thực 6 chữ số"), "123456");
    await selectTab(user, "Mã khôi phục");
    await user.type(screen.getByLabelText("Mã khôi phục"), "  ABCD-EFGH  ");
    await fillPassword(user);
    await user.click(signInButton());
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(JSON.parse(String(callsTo(fn, "/auth/login/totp")[0][1].body))).toEqual({ mfa_token: "tok", recovery_code: "abcd-efgh" });
  });

  it("shows the step-two screen when no code was filled in", async () => {
    const fn = setup(PLAIN, withMfa);
    const user = await open();
    await fillPassword(user);
    await user.click(signInButton());
    expect(await screen.findByRole("heading", { name: "Xác minh danh tính" })).toBeInTheDocument();
    expect(callsTo(fn, "/auth/login/totp")).toHaveLength(0);
    expect(goTo).not.toHaveBeenCalled();
  });

  it("shows the server message when the code is wrong and does not sign in", async () => {
    setup(PLAIN, (url) =>
      url.endsWith("/auth/login") ? jsonResponse(MFA_TOTP) : url.endsWith("/auth/login/totp") ? jsonResponse({ detail: "bad" }, 401) : undefined,
    );
    const user = await open();
    await selectTab(user, "Mã TOTP");
    await user.type(screen.getByLabelText("Mã xác thực 6 chữ số"), "123456");
    await fillPassword(user);
    await user.click(signInButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Mã không đúng hoặc đã dùng");
    expect(goTo).not.toHaveBeenCalled();
  });

  it("keeps the code tabs usable only for sign-in: they hold digits and nothing else", async () => {
    setup();
    const user = await open();
    await selectTab(user, "Mã TOTP");
    const input = screen.getByLabelText("Mã xác thực 6 chữ số");
    await user.type(input, "12ab34cd56789");
    expect(input).toHaveValue("123456");
  });
});
