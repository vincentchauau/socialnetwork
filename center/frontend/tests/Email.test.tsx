import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AccountView from "../app/components/AccountView";
import ForgotPasswordForm from "../app/components/ForgotPasswordForm";
import LoginFlow from "../app/components/LoginFlow";
import MagicLoginView from "../app/components/MagicLoginView";
import ResetPasswordForm from "../app/components/ResetPasswordForm";
import VerifyEmailView from "../app/components/VerifyEmailView";
import * as forgotPage from "../app/forgot-password/page";
import * as magicPage from "../app/login/magic/page";
import * as resetPage from "../app/reset-password/page";
import * as verifyPage from "../app/verify-email/page";
import { parseToken } from "../app/hooks/useUrlToken";
import { NEUTRAL_RESET_MESSAGE, NEUTRAL_SIGN_IN_MESSAGE, takeVerificationEmail } from "../app/lib/auth";
import { jsonResponse, me, mockFetch, session } from "./helpers";

const goTo = vi.hoisted(() => vi.fn());
vi.mock("../app/lib/navigate", async (original) => ({
  ...(await original<typeof import("../app/lib/navigate")>()),
  goTo,
}));

vi.mock("@simplewebauthn/browser", () => ({
  browserSupportsWebAuthn: () => true,
  startAuthentication: vi.fn(),
  startRegistration: vi.fn(),
}));

const ON = { google_client_id: null, biometrics_enabled: false, email_enabled: true };
const OFF = { google_client_id: null, biometrics_enabled: false, email_enabled: false };
const NEUTRAL = "Nếu email này thuộc một tài khoản, chúng tôi đã gửi mã và liên kết đăng nhập.";

type Handler = (url: string, init: RequestInit) => Response | undefined;

function setup(config: unknown = ON, extra?: Handler) {
  return mockFetch((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/config")) return jsonResponse(config);
    if (url.endsWith("/email/login/request")) return jsonResponse({ ok: true }, 202);
    if (url.endsWith("/email/login/verify") || url.endsWith("/email/login/magic")) return jsonResponse(session);
    if (url.endsWith("/register/combined")) return jsonResponse(session, 201);
    return jsonResponse({ detail: "unexpected " + url }, 500);
  });
}

const callsTo = (fetchMock: ReturnType<typeof setup>, suffix: string) =>
  fetchMock.mock.calls.filter(([url]) => url.endsWith(suffix));
const bodyOf = (fetchMock: ReturnType<typeof setup>, suffix: string) =>
  JSON.parse(String(callsTo(fetchMock, suffix)[0][1].body));
const noTokenInUrls = (fetchMock: ReturnType<typeof setup>, token: string) =>
  fetchMock.mock.calls.every(([url]) => !url.includes(token));

beforeEach(() => {
  goTo.mockReset();
  window.sessionStorage.clear();
  window.history.replaceState({}, "", "/login");
});

afterEach(() => {
  vi.useRealTimers();
});

async function openEmailTab(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("tab", { name: "Email" }));
}

async function sendCode(user: ReturnType<typeof userEvent.setup>, address = "ann@example.com") {
  await openEmailTab(user);
  await user.type(screen.getByLabelText("Email", { selector: "input" }), address);
  await user.click(screen.getByRole("button", { name: "Gửi mã đăng nhập" }));
  await screen.findByLabelText("Mã 6 chữ số");
}

describe("Email sign-in tab", () => {
  it("hides every email control when email is disabled", async () => {
    setup(OFF);
    render(<LoginFlow />);
    await screen.findByRole("tab", { name: "Passkey" });
    expect(screen.queryByRole("tab", { name: "Email" })).not.toBeInTheDocument();
    expect(screen.queryByText("Quên mật khẩu?")).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Chưa có tài khoản? Đăng ký" }));
    expect(screen.queryByLabelText(/^Email/)).not.toBeInTheDocument();
  });

  it("keeps Mật khẩu as default tab and links to forgot-password", async () => {
    setup();
    render(<LoginFlow />);
    await screen.findByRole("tab", { name: "Email" });
    expect(screen.getByRole("tab", { name: "Mật khẩu" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("link", { name: "Quên mật khẩu?" })).toHaveAttribute("href", "/forgot-password");
  });

  it("supports arrow-key navigation onto the Email tab", async () => {
    setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    const password = await screen.findByRole("tab", { name: "Mật khẩu" });
    await screen.findByRole("tab", { name: "Email" });
    password.focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Email" })).toHaveAttribute("aria-selected", "true");
  });

  it("sends the code, shows the neutral message and signs in with the 6-digit code", async () => {
    const fetchMock = setup();
    window.history.replaceState({}, "", "/login?next=/account");
    const user = userEvent.setup();
    render(<LoginFlow />);
    await sendCode(user);
    expect(bodyOf(fetchMock, "/email/login/request")).toEqual({ email: "ann@example.com" });
    expect(screen.getByText(NEUTRAL)).toBeInTheDocument();
    const code = screen.getByLabelText("Mã 6 chữ số");
    expect(code).toHaveAttribute("inputmode", "numeric");
    expect(code).toHaveAttribute("autocomplete", "one-time-code");
    await user.type(code, "123456");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/account"));
    expect(bodyOf(fetchMock, "/email/login/verify")).toEqual({ email: "ann@example.com", code: "123456" });
  });

  it("shows the same neutral message for any address", async () => {
    setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await sendCode(user, "nobody@example.com");
    expect(screen.getByText(NEUTRAL_SIGN_IN_MESSAGE)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Đổi email" }));
    expect(screen.getByLabelText("Email", { selector: "input" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Mã 6 chữ số")).not.toBeInTheDocument();
  });

  it("rejects a malformed address and a malformed code without calling the server", async () => {
    const fetchMock = setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await openEmailTab(user);
    await user.type(screen.getByLabelText("Email", { selector: "input" }), "a@b");
    fireEvent.submit(screen.getByRole("form", { name: "Đăng nhập bằng email" }));
    expect(await screen.findByText("Email không hợp lệ")).toBeInTheDocument();
    expect(callsTo(fetchMock, "/email/login/request")).toHaveLength(0);
    await user.clear(screen.getByLabelText("Email", { selector: "input" }));
    await user.type(screen.getByLabelText("Email", { selector: "input" }), "ann@example.com");
    await user.click(screen.getByRole("button", { name: "Gửi mã đăng nhập" }));
    await user.type(await screen.findByLabelText("Mã 6 chữ số"), "12");
    fireEvent.submit(screen.getByRole("form", { name: "Nhập mã đăng nhập" }));
    expect(await screen.findByText("Mã gồm 6 chữ số")).toBeInTheDocument();
    expect(callsTo(fetchMock, "/email/login/verify")).toHaveLength(0);
  });

  it("shows the server text for a wrong code and stays on the code step", async () => {
    setup(ON, (url) =>
      url.endsWith("/email/login/verify") ? jsonResponse({ detail: "Invalid or expired code" }, 401) : undefined,
    );
    const user = userEvent.setup();
    render(<LoginFlow />);
    await sendCode(user);
    await user.type(screen.getByLabelText("Mã 6 chữ số"), "000000");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
    expect(await screen.findByText("Invalid or expired code")).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Mã 6 chữ số")).toBeInTheDocument();
  });

  it("hands mfa_required to the existing verification step", async () => {
    setup(ON, (url) =>
      url.endsWith("/email/login/verify") ? jsonResponse({ mfa_required: true, mfa_token: "m1" }) : undefined,
    );
    const user = userEvent.setup();
    render(<LoginFlow />);
    await sendCode(user);
    await user.type(screen.getByLabelText("Mã 6 chữ số"), "123456");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
    expect(await screen.findByRole("heading", { name: "Xác minh danh tính" })).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });

  it("shows the throttling text on 429 and stays on the email step", async () => {
    setup(ON, (url) =>
      url.endsWith("/email/login/request") ? jsonResponse({ detail: "Too many attempts, try later" }, 429) : undefined,
    );
    const user = userEvent.setup();
    render(<LoginFlow />);
    await openEmailTab(user);
    await user.type(screen.getByLabelText("Email", { selector: "input" }), "ann@example.com");
    await user.click(screen.getByRole("button", { name: "Gửi mã đăng nhập" }));
    expect(await screen.findByText("Thử quá nhiều lần, hãy thử lại sau")).toBeInTheDocument();
    expect(screen.queryByLabelText("Mã 6 chữ số")).not.toBeInTheDocument();
  });

  it("disables resend for 30 seconds, then allows it again", async () => {
    const fetchMock = setup();
    render(<LoginFlow />);
    await screen.findByRole("tab", { name: "Email" });
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("tab", { name: "Email" }));
    fireEvent.change(screen.getByLabelText("Email", { selector: "input" }), { target: { value: "ann@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Gửi mã đăng nhập" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const resend = screen.getByRole("button", { name: /^Gửi lại/ });
    expect(resend).toBeDisabled();
    expect(resend).toHaveTextContent("Gửi lại (30s)");
    for (let second = 0; second < 29; second += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_000);
      });
    }
    expect(screen.getByRole("button", { name: /^Gửi lại/ })).toBeDisabled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    const ready = screen.getByRole("button", { name: "Gửi lại" });
    expect(ready).toBeEnabled();
    fireEvent.click(ready);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(callsTo(fetchMock, "/email/login/request").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("button", { name: /^Gửi lại/ })).toBeDisabled();
  });
});

describe("Forgot password page", () => {
  it("always confirms with the same neutral text", async () => {
    const fetchMock = setup(ON, (url) => (url.endsWith("/password/forgot") ? jsonResponse({ ok: true }, 202) : undefined));
    const user = userEvent.setup();
    render(<ForgotPasswordForm />);
    await user.type(screen.getByLabelText("Email", { selector: "input" }), "who@example.com");
    await user.click(screen.getByRole("button", { name: "Gửi liên kết đặt lại" }));
    expect(await screen.findByText(NEUTRAL_RESET_MESSAGE)).toBeInTheDocument();
    expect(bodyOf(fetchMock, "/password/forgot")).toEqual({ email: "who@example.com" });
    expect(screen.getByRole("link", { name: "Quay lại đăng nhập" })).toHaveAttribute("href", "/login");
  });

  it("validates the address and surfaces 429", async () => {
    const fetchMock = setup(ON, (url) =>
      url.endsWith("/password/forgot") ? jsonResponse({ detail: "Too many attempts, try later" }, 429) : undefined,
    );
    const user = userEvent.setup();
    render(<ForgotPasswordForm />);
    await user.type(screen.getByLabelText("Email", { selector: "input" }), "bad");
    fireEvent.submit(screen.getByRole("form", { name: "Quên mật khẩu" }));
    expect(await screen.findByText("Email không hợp lệ")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    await user.clear(screen.getByLabelText("Email", { selector: "input" }));
    await user.type(screen.getByLabelText("Email", { selector: "input" }), "ann@example.com");
    await user.click(screen.getByRole("button", { name: "Gửi liên kết đặt lại" }));
    expect(await screen.findByText("Thử quá nhiều lần, hãy thử lại sau")).toBeInTheDocument();
  });
});

describe("Reset password page", () => {
  const SECRET = "tok-secret-1";

  it("reads the token, removes it from the address bar and resets the password", async () => {
    window.history.replaceState({}, "", `/reset-password#token=${SECRET}`);
    const fetchMock = setup(ON, (url) => (url.endsWith("/password/reset") ? jsonResponse({ ok: true }) : undefined));
    const user = userEvent.setup();
    render(<ResetPasswordForm />);
    await screen.findByRole("form", { name: "Đặt lại mật khẩu" });
    expect(window.location.search + window.location.hash).toBe("");
    expect(window.location.href).not.toContain(SECRET);
    await user.type(screen.getByLabelText("Mật khẩu mới"), "newpassword1");
    expect(screen.getByText("Mật khẩu đủ dài.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Nhập lại mật khẩu mới"), "newpassword1");
    await user.click(screen.getByRole("button", { name: "Đổi mật khẩu" }));
    expect(await screen.findByText("Đã đổi mật khẩu. Hãy đăng nhập lại.")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "/password/reset")).toEqual({ token: SECRET, new_password: "newpassword1" });
    expect(noTokenInUrls(fetchMock, SECRET)).toBe(true);
    expect(screen.getByRole("link", { name: "Đăng nhập" })).toHaveAttribute("href", "/login");
  });

  it("validates length and confirmation before calling the server", async () => {
    window.history.replaceState({}, "", `/reset-password#token=${SECRET}`);
    const fetchMock = setup();
    const user = userEvent.setup();
    render(<ResetPasswordForm />);
    await user.type(await screen.findByLabelText("Mật khẩu mới"), "short");
    await user.type(screen.getByLabelText("Nhập lại mật khẩu mới"), "short");
    await user.click(screen.getByRole("button", { name: "Đổi mật khẩu" }));
    expect(await screen.findByText("Mật khẩu cần ít nhất 8 ký tự")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Mật khẩu mới"));
    await user.type(screen.getByLabelText("Mật khẩu mới"), "longenough1");
    await user.click(screen.getByRole("button", { name: "Đổi mật khẩu" }));
    expect(await screen.findByText("Mật khẩu nhập lại không khớp")).toBeInTheDocument();
    expect(callsTo(fetchMock, "/password/reset")).toHaveLength(0);
  });

  it("shows the invalid-link state with a link to request a new one on 400", async () => {
    window.history.replaceState({}, "", `/reset-password#token=${SECRET}`);
    setup(ON, (url) =>
      url.endsWith("/password/reset") ? jsonResponse({ detail: "Invalid or expired link" }, 400) : undefined,
    );
    const user = userEvent.setup();
    render(<ResetPasswordForm />);
    await user.type(await screen.findByLabelText("Mật khẩu mới"), "newpassword1");
    await user.type(screen.getByLabelText("Nhập lại mật khẩu mới"), "newpassword1");
    await user.click(screen.getByRole("button", { name: "Đổi mật khẩu" }));
    expect(await screen.findByText("Liên kết không hợp lệ hoặc đã hết hạn.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Yêu cầu liên kết mới" })).toHaveAttribute("href", "/forgot-password");
  });

  it("keeps the form and shows the policy message on 422", async () => {
    window.history.replaceState({}, "", `/reset-password#token=${SECRET}`);
    setup(ON, (url) =>
      url.endsWith("/password/reset") ? jsonResponse({ detail: "Password is too common" }, 422) : undefined,
    );
    const user = userEvent.setup();
    render(<ResetPasswordForm />);
    await user.type(await screen.findByLabelText("Mật khẩu mới"), "password123");
    await user.type(screen.getByLabelText("Nhập lại mật khẩu mới"), "password123");
    await user.click(screen.getByRole("button", { name: "Đổi mật khẩu" }));
    expect(await screen.findByText("Password is too common")).toBeInTheDocument();
    expect(screen.getByLabelText("Mật khẩu mới")).toBeInTheDocument();
  });

  it("shows the invalid-link state when there is no token", async () => {
    window.history.replaceState({}, "", "/reset-password");
    render(<ResetPasswordForm />);
    expect(await screen.findByText("Liên kết không hợp lệ hoặc đã hết hạn.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Mật khẩu mới")).not.toBeInTheDocument();
  });
});

describe("Verify email page", () => {
  const SECRET = "verify-secret-1";

  it("does not call the server on load, only when the button is pressed", async () => {
    window.history.replaceState({}, "", `/verify-email#token=${SECRET}`);
    const fetchMock = setup(ON, (url) =>
      url.endsWith("/email/verify") ? jsonResponse({ email: "ann@example.com", email_verified: true }) : undefined,
    );
    const user = userEvent.setup();
    render(<VerifyEmailView />);
    const button = await screen.findByRole("button", { name: "Xác nhận email" });
    expect(window.location.search + window.location.hash).toBe("");
    expect(fetchMock).not.toHaveBeenCalled();
    await user.click(button);
    expect(await screen.findByText("Đã xác nhận email.")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "/email/verify")).toEqual({ token: SECRET });
    expect(noTokenInUrls(fetchMock, SECRET)).toBe(true);
  });

  it("shows a failure state for an invalid or expired link", async () => {
    window.history.replaceState({}, "", `/verify-email#token=${SECRET}`);
    setup(ON, (url) =>
      url.endsWith("/email/verify") ? jsonResponse({ detail: "Invalid or expired link" }, 400) : undefined,
    );
    const user = userEvent.setup();
    render(<VerifyEmailView />);
    await user.click(await screen.findByRole("button", { name: "Xác nhận email" }));
    expect(await screen.findByText(/Liên kết không hợp lệ hoặc đã hết hạn\./)).toBeInTheDocument();
  });

  it("reports a missing token without a confirm button", async () => {
    window.history.replaceState({}, "", "/verify-email");
    render(<VerifyEmailView />);
    expect(await screen.findByText("Liên kết không hợp lệ hoặc đã hết hạn.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xác nhận email" })).not.toBeInTheDocument();
  });
});

describe("Magic link page", () => {
  const SECRET = "magic-secret-1";

  it("signs in only after the click and redirects like a sign-in", async () => {
    window.history.replaceState({}, "", `/login/magic?next=/account#token=${SECRET}`);
    const fetchMock = setup();
    const user = userEvent.setup();
    render(<MagicLoginView />);
    const button = await screen.findByRole("button", { name: "Đăng nhập" });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(window.location.search + window.location.hash).toBe("");
    await user.click(button);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(bodyOf(fetchMock, "/email/login/magic")).toEqual({ token: SECRET });
    expect(noTokenInUrls(fetchMock, SECRET)).toBe(true);
  });

  it("hands a pending second factor to the verification step and finishes with the authenticator code", async () => {
    window.history.replaceState({}, "", `/login/magic#token=${SECRET}`);
    const fetchMock = setup(ON, (url) => {
      if (url.endsWith("/email/login/magic")) return jsonResponse({ mfa_required: true, mfa_token: "m1", factors: ["totp"] });
      if (url.endsWith("/login/totp")) return jsonResponse(session);
      return undefined;
    });
    const user = userEvent.setup();
    render(<MagicLoginView />);
    await user.click(await screen.findByRole("button", { name: "Đăng nhập" }));
    expect(await screen.findByRole("heading", { name: "Xác minh danh tính" })).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText("Mã xác thực 6 chữ số"), "123456");
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(bodyOf(fetchMock, "/login/totp")).toEqual({ mfa_token: "m1", code: "123456" });
  });

  it("goes to /login when the second-factor step is cancelled", async () => {
    window.history.replaceState({}, "", `/login/magic#token=${SECRET}`);
    setup(ON, (url) =>
      url.endsWith("/email/login/magic") ? jsonResponse({ mfa_required: true, mfa_token: "m1", factors: ["totp"] }) : undefined,
    );
    const user = userEvent.setup();
    render(<MagicLoginView />);
    await user.click(await screen.findByRole("button", { name: "Đăng nhập" }));
    await user.click(await screen.findByRole("button", { name: "Hủy" }));
    expect(goTo).toHaveBeenCalledWith("/login");
  });

  it("shows a failure state for an invalid link", async () => {
    window.history.replaceState({}, "", `/login/magic#token=${SECRET}`);
    setup(ON, (url) =>
      url.endsWith("/email/login/magic") ? jsonResponse({ detail: "Invalid or expired link" }, 401) : undefined,
    );
    const user = userEvent.setup();
    render(<MagicLoginView />);
    await user.click(await screen.findByRole("button", { name: "Đăng nhập" }));
    expect(await screen.findByText("Liên kết không hợp lệ hoặc đã hết hạn.")).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });
});

describe("Register email field", () => {
  async function openRegister(user: ReturnType<typeof userEvent.setup>) {
    await screen.findByRole("tab", { name: "Passkey" });
    await user.click(screen.getByRole("button", { name: "Chưa có tài khoản? Đăng ký" }));
  }
  async function fillAccount(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText("Tên đăng nhập"), "ann");
    await user.type(screen.getByLabelText("Mật khẩu", { selector: "input[type=password]" }), "password1");
  }
  const formOf = (fetchMock: ReturnType<typeof setup>) =>
    callsTo(fetchMock, "/register/combined")[0][1].body as FormData;

  it("is optional, omitted when blank and not a method checkbox", async () => {
    const fetchMock = setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await openRegister(user);
    expect(screen.getByLabelText("Email (tùy chọn, dùng để khôi phục tài khoản)")).not.toBeRequired();
    expect(screen.queryByRole("checkbox", { name: /Email/ })).not.toBeInTheDocument();
    await fillAccount(user);
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    await waitFor(() => expect(goTo).toHaveBeenCalled());
    expect(formOf(fetchMock).has("email")).toBe(false);
    expect(takeVerificationEmail()).toBeNull();
  });

  it("sends the email field and remembers the one-time notice", async () => {
    const fetchMock = setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await openRegister(user);
    await fillAccount(user);
    await user.type(screen.getByLabelText("Email (tùy chọn, dùng để khôi phục tài khoản)"), " ann@example.com ");
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    await waitFor(() => expect(goTo).toHaveBeenCalled());
    expect(formOf(fetchMock).get("email")).toBe("ann@example.com");
    expect(takeVerificationEmail()).toBe("ann@example.com");
    expect(takeVerificationEmail()).toBeNull();
  });

  it("rejects a malformed email before calling the server", async () => {
    const fetchMock = setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await openRegister(user);
    await fillAccount(user);
    await user.type(screen.getByLabelText("Email (tùy chọn, dùng để khôi phục tài khoản)"), "nope");
    fireEvent.submit(screen.getByRole("form", { name: "Đăng ký" }));
    expect(await screen.findByText("Email không hợp lệ")).toBeInTheDocument();
    expect(callsTo(fetchMock, "/register/combined")).toHaveLength(0);
  });
});

describe("Account email row", () => {
  function setupAccount(account: Partial<typeof me> = {}, extra?: Handler) {
    let current = { ...me, ...account };
    const fetchMock = mockFetch((url, init) => {
      const custom = extra?.(url, init);
      if (custom) return custom;
      if (url.endsWith("/auth/config")) return jsonResponse(ON);
      if (url.endsWith("/auth/me") && (init.method ?? "GET") === "GET") return jsonResponse(current);
      if (url.endsWith("/auth/me/email") && init.method === "POST") {
        current = { ...current, email: JSON.parse(String(init.body)).email, email_verified: false };
        return jsonResponse({ ok: true }, 202);
      }
      if (url.endsWith("/auth/me/email") && init.method === "DELETE") {
        current = { ...current, email: null, email_verified: false };
        return jsonResponse({ has_password: true });
      }
      if (url.endsWith("/auth/email/verify")) {
        current = { ...current, email_verified: true };
        return jsonResponse({ email: current.email, email_verified: true });
      }
      return jsonResponse({});
    });
    return fetchMock;
  }

  async function rowFor(name: string) {
    const section = await screen.findByRole("region", { name: "Các cách đăng nhập" });
    return within(section).getAllByRole("listitem").find((li) => li.textContent?.startsWith(`${name}:`))!;
  }

  it("shows chưa có with the explanatory note and no code entry", async () => {
    setupAccount();
    render(<AccountView />);
    const email = await rowFor("Email");
    expect(email).toHaveTextContent("Email: chưa có");
    expect(email).toHaveTextContent("Email đã xác minh dùng để đăng nhập, khôi phục tài khoản và nhận thông báo bảo mật.");
    expect(within(email).queryByLabelText(/Mã xác minh/)).not.toBeInTheDocument();
    expect(within(email).getByRole("button", { name: "Thêm email" })).toBeInTheDocument();
    expect(within(email).queryByRole("button", { name: "Xóa email" })).not.toBeInTheDocument();
  });

  it("shows an unverified address with code entry, verifies, and reloads", async () => {
    const fetchMock = setupAccount({ email: "ann@example.com", email_verified: false });
    const user = userEvent.setup();
    render(<AccountView />);
    const before = await rowFor("Email");
    expect(before).toHaveTextContent("ann@example.com (chưa xác minh)");
    await user.type(within(before).getByLabelText(/Mã xác minh/), "123456");
    await user.click(within(before).getByRole("button", { name: "Xác minh" }));
    await waitFor(async () => expect(await rowFor("Email")).toHaveTextContent("ann@example.com (đã xác minh)"));
    expect(bodyOf(fetchMock, "/auth/email/verify")).toEqual({ code: "123456" });
    expect((await rowFor("Email")).querySelector("form[aria-label='Xác minh email']")).toBeNull();
  });

  it("rejects a malformed verification code locally and shows the server text for a wrong one", async () => {
    setupAccount({ email: "ann@example.com" }, (url) =>
      url.endsWith("/auth/email/verify") ? jsonResponse({ detail: "Invalid or expired code" }, 400) : undefined,
    );
    const user = userEvent.setup();
    render(<AccountView />);
    const email = await rowFor("Email");
    await user.type(within(email).getByLabelText(/Mã xác minh/), "12");
    await user.click(within(email).getByRole("button", { name: "Xác minh" }));
    expect(await screen.findByText("Mã gồm 6 chữ số")).toBeInTheDocument();
    await user.type(within(email).getByLabelText(/Mã xác minh/), "3456");
    await user.click(within(email).getByRole("button", { name: "Xác minh" }));
    expect(await screen.findByText("Invalid or expired code")).toBeInTheDocument();
  });

  it("shows a verified address", async () => {
    setupAccount({ email: "ann@example.com", email_verified: true });
    render(<AccountView />);
    const email = await rowFor("Email");
    expect(email).toHaveTextContent("ann@example.com (đã xác minh)");
    expect(within(email).queryByLabelText(/Mã xác minh/)).not.toBeInTheDocument();
    expect(within(email).getByRole("button", { name: "Đổi email" })).toBeInTheDocument();
  });

  it("sets an email with the password for accounts that have one", async () => {
    const fetchMock = setupAccount();
    const user = userEvent.setup();
    render(<AccountView />);
    const email = await rowFor("Email");
    await user.type(within(email).getByLabelText("Địa chỉ email"), "new@example.com");
    await user.type(within(email).getByLabelText("Nhập lại mật khẩu để xác nhận"), "secret-pass");
    await user.click(within(email).getByRole("button", { name: "Thêm email" }));
    await waitFor(async () => expect(await rowFor("Email")).toHaveTextContent("new@example.com (chưa xác minh)"));
    expect(bodyOf(fetchMock, "/auth/me/email")).toEqual({ email: "new@example.com", password: "secret-pass" });
    expect(await screen.findByText("Chúng tôi đã gửi mã xác minh tới new@example.com.")).toBeInTheDocument();
    expect(within(await rowFor("Email")).getByLabelText(/Mã xác minh/)).toBeInTheDocument();
  });

  it("sets an email without a password field when the account has none", async () => {
    const fetchMock = setupAccount({ has_password: false });
    const user = userEvent.setup();
    render(<AccountView />);
    const email = await rowFor("Email");
    expect(within(email).queryByLabelText("Nhập lại mật khẩu để xác nhận")).not.toBeInTheDocument();
    await user.type(within(email).getByLabelText("Địa chỉ email"), "new@example.com");
    await user.click(within(email).getByRole("button", { name: "Thêm email" }));
    await waitFor(() => expect(callsTo(fetchMock, "/auth/me/email").length).toBeGreaterThan(0));
    const sent = bodyOf(fetchMock, "/auth/me/email");
    expect(sent.email).toBe("new@example.com");
    expect(sent.password).toBeUndefined();
  });

  it("shows server errors for a taken email and a wrong password", async () => {
    setupAccount({}, (url, init) =>
      url.endsWith("/auth/me/email") && init.method === "POST"
        ? jsonResponse({ detail: "Email already in use" }, 409)
        : undefined,
    );
    const user = userEvent.setup();
    render(<AccountView />);
    const email = await rowFor("Email");
    await user.type(within(email).getByLabelText("Địa chỉ email"), "taken@example.com");
    await user.click(within(email).getByRole("button", { name: "Thêm email" }));
    expect(await screen.findByText("Email already in use")).toBeInTheDocument();
  });

  it("rejects a malformed address locally", async () => {
    const fetchMock = setupAccount();
    const user = userEvent.setup();
    render(<AccountView />);
    const email = await rowFor("Email");
    await user.type(within(email).getByLabelText("Địa chỉ email"), "bad");
    fireEvent.submit(within(email).getByRole("form", { name: "Thêm email" }));
    expect(await screen.findByText("Email không hợp lệ")).toBeInTheDocument();
    expect(callsTo(fetchMock, "/auth/me/email")).toHaveLength(0);
  });

  it("resends the code for the current address", async () => {
    const fetchMock = setupAccount({ email: "ann@example.com" });
    const user = userEvent.setup();
    render(<AccountView />);
    const email = await rowFor("Email");
    await user.type(within(email).getByLabelText("Nhập lại mật khẩu để xác nhận"), "secret-pass");
    await user.click(within(email).getByRole("button", { name: "Gửi lại" }));
    expect(await screen.findByText("Đã gửi lại mã xác minh tới ann@example.com.")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "/auth/me/email")).toEqual({ email: "ann@example.com", password: "secret-pass" });
  });

  it("removes the email with the password and reloads", async () => {
    const fetchMock = setupAccount({ email: "ann@example.com", email_verified: true });
    const user = userEvent.setup();
    render(<AccountView />);
    const email = await rowFor("Email");
    await user.type(within(email).getByLabelText("Nhập lại mật khẩu để xác nhận"), "secret-pass");
    await user.click(within(email).getByRole("button", { name: "Xóa email" }));
    await waitFor(async () => expect(await rowFor("Email")).toHaveTextContent("Email: chưa có"));
    const call = fetchMock.mock.calls.find(([url, init]) => url.endsWith("/auth/me/email") && init.method === "DELETE")!;
    expect(JSON.parse(String(call[1].body))).toEqual({ password: "secret-pass" });
  });

  it("shows the server 409 text when the email is the last sign-in method", async () => {
    setupAccount({ email: "ann@example.com", email_verified: true }, (url, init) =>
      url.endsWith("/auth/me/email") && init.method === "DELETE"
        ? jsonResponse({ detail: "Keep at least one sign-in method" }, 409)
        : undefined,
    );
    const user = userEvent.setup();
    render(<AccountView />);
    const email = await rowFor("Email");
    await user.click(within(email).getByRole("button", { name: "Xóa email" }));
    expect(await screen.findByText("Keep at least one sign-in method")).toBeInTheDocument();
    expect(await rowFor("Email")).toHaveTextContent("ann@example.com (đã xác minh)");
  });

  it("hides the email row when email is disabled", async () => {
    mockFetch((url, init) => {
      if (url.endsWith("/auth/config")) return jsonResponse(OFF);
      if (url.endsWith("/auth/me") && (init.method ?? "GET") === "GET") return jsonResponse({ ...me, email: "ann@example.com" });
      return jsonResponse({});
    });
    render(<AccountView />);
    await screen.findByRole("region", { name: "Các cách đăng nhập" });
    expect(screen.queryByText(/Email đã xác minh dùng để đăng nhập/)).not.toBeInTheDocument();
    expect(screen.getByText("Email: ann@example.com")).toBeInTheDocument();
  });
});

describe("Token in the URL fragment", () => {
  const SECRET = "frag-secret-1";

  it("parses the fragment, falls back to the query and rejects empty or malformed input", () => {
    expect(parseToken(`#token=${SECRET}`, "")).toBe(SECRET);
    expect(parseToken(`#a=1&token=${SECRET}`, "")).toBe(SECRET);
    expect(parseToken("", `?token=${SECRET}`)).toBe(SECRET);
    expect(parseToken(`#token=${SECRET}`, "?token=other")).toBe(SECRET);
    expect(parseToken("#token=", "")).toBeNull();
    expect(parseToken("#", "")).toBeNull();
    expect(parseToken("#%zz&=&token", "")).toBeNull();
    expect(parseToken("", "")).toBeNull();
  });

  it("still accepts a legacy query link and clears it from the address bar", async () => {
    window.history.replaceState({}, "", `/verify-email?token=${SECRET}`);
    const fetchMock = setup(ON, (url) =>
      url.endsWith("/email/verify") ? jsonResponse({ email: "ann@example.com", email_verified: true }) : undefined,
    );
    render(<VerifyEmailView />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Xác nhận email" }));
    expect(await screen.findByText("Đã xác nhận email.")).toBeInTheDocument();
    expect(window.location.search + window.location.hash).toBe("");
    expect(bodyOf(fetchMock, "/email/verify")).toEqual({ token: SECRET });
  });

  it("clears the fragment, keeps the token out of the DOM and out of request URLs", async () => {
    window.history.replaceState({}, "", `/login/magic#token=${SECRET}`);
    const fetchMock = setup();
    const { container } = render(<MagicLoginView />);
    await screen.findByRole("button", { name: "Đăng nhập" });
    expect(window.location.href).not.toContain(SECRET);
    expect(container.innerHTML).not.toContain(SECRET);
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.setup().click(screen.getByRole("button", { name: "Đăng nhập" }));
    await waitFor(() => expect(goTo).toHaveBeenCalled());
    expect(noTokenInUrls(fetchMock, SECRET)).toBe(true);
  });

  it("treats an empty or malformed fragment as a missing token", async () => {
    window.history.replaceState({}, "", "/verify-email#token=");
    render(<VerifyEmailView />);
    expect(await screen.findByText("Liên kết không hợp lệ hoặc đã hết hạn.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xác nhận email" })).not.toBeInTheDocument();
    expect(window.location.hash).toBe("");
  });

  it.each([
    ["verify-email", verifyPage],
    ["login/magic", magicPage],
    ["reset-password", resetPage],
    ["forgot-password", forgotPage],
  ])("exports a no-referrer policy for /%s", (_route, page) => {
    expect(page.metadata.referrer).toBe("no-referrer");
  });
});
