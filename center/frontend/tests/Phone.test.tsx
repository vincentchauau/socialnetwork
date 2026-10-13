import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AccountView from "../app/components/AccountView";
import LoginFlow from "../app/components/LoginFlow";
import PhoneMethod from "../app/components/PhoneMethod";
import { isPhoneValid, normalizePhone } from "../app/lib/auth";
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

const ON = { google_client_id: null, biometrics_enabled: false, email_enabled: false, phone_enabled: true };
const OFF = { ...ON, phone_enabled: false };
const NEUTRAL = "Nếu số điện thoại này thuộc một tài khoản, chúng tôi đã gửi mã đăng nhập qua SMS.";
const WARNING = "SMS kém an toàn hơn Passkey hoặc ứng dụng xác thực (có thể bị đánh cắp SIM)";

type Handler = (url: string, init: RequestInit) => Response | undefined;
type User = ReturnType<typeof userEvent.setup>;

function setup(config: unknown = ON, extra?: Handler, profile: Record<string, unknown> = {}) {
  return mockFetch((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/config")) return jsonResponse(config);
    if (url.endsWith("/auth/me") && (init.method ?? "GET") === "GET") return jsonResponse({ ...me, ...profile });
    if (url.endsWith("/phone/login/request")) return jsonResponse({ ok: true }, 202);
    if (url.endsWith("/phone/login/verify")) return jsonResponse(session);
    if (url.endsWith("/auth/me/phone") || url.endsWith("/auth/me/phone/verify")) return jsonResponse({ ok: true }, init.method === "POST" && url.endsWith("/phone") ? 202 : 200);
    return jsonResponse({ detail: "unexpected " + url }, 500);
  });
}

const callsTo = (fn: ReturnType<typeof setup>, suffix: string, method?: string) =>
  fn.mock.calls.filter(([url, init]) => url.endsWith(suffix) && (!method || (init.method ?? "GET") === method));
const bodyOf = (fn: ReturnType<typeof setup>, suffix: string, method?: string) =>
  JSON.parse(String(callsTo(fn, suffix, method)[0][1].body));

beforeEach(() => {
  goTo.mockReset();
  window.history.replaceState({}, "", "/login");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("phone helpers", () => {
  it("normalizes separators and validates E.164", () => {
    expect(normalizePhone("+84 (901) 234-567")).toBe("+84901234567");
    expect(isPhoneValid("+84 901 234 567")).toBe(true);
    expect(isPhoneValid("0901234567")).toBe(false);
    expect(isPhoneValid("+12")).toBe(false);
    expect(isPhoneValid("+84abc")).toBe(false);
  });
});

async function openPhoneTab(user: User) {
  await user.click(await screen.findByRole("tab", { name: "Điện thoại" }));
}

async function requestCode(user: User, number = "+84901234567") {
  await openPhoneTab(user);
  await user.type(screen.getByLabelText("Số điện thoại"), number);
  await user.click(screen.getByRole("button", { name: "Gửi mã SMS" }));
  await screen.findByLabelText("Mã 6 chữ số");
}

describe("phone sign-in tab", () => {
  it("is hidden unless the server enables phone sign-in", async () => {
    setup(OFF);
    render(<LoginFlow />);
    await screen.findByRole("tab", { name: "Passkey" });
    expect(screen.queryByRole("tab", { name: "Điện thoại" })).not.toBeInTheDocument();
  });

  it("is shown after Mật khẩu with a tel input, autocomplete and hint", async () => {
    setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await openPhoneTab(user);
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Mật khẩu", "Điện thoại", "Passkey", "Mã QR"]);
    const input = screen.getByLabelText("Số điện thoại");
    expect(input).toHaveAttribute("type", "tel");
    expect(input).toHaveAttribute("autocomplete", "tel");
    expect(input).toHaveAttribute("placeholder", "+84901234567");
  });

  it("sits after the Email tab when both are enabled", async () => {
    setup({ ...ON, email_enabled: true });
    render(<LoginFlow />);
    await screen.findByRole("tab", { name: "Điện thoại" });
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Mật khẩu", "Email", "Điện thoại", "Passkey", "Mã QR"]);
  });

  it("rejects a number that is not international without calling the server", async () => {
    const fn = setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await openPhoneTab(user);
    await user.type(screen.getByLabelText("Số điện thoại"), "0901234567");
    await user.click(screen.getByRole("button", { name: "Gửi mã SMS" }));
    expect(await screen.findByText(/Số điện thoại không hợp lệ/)).toBeInTheDocument();
    expect(callsTo(fn, "/phone/login/request")).toHaveLength(0);
  });

  it("requests a code, shows the neutral message and signs in with the 6-digit code", async () => {
    const fn = setup();
    window.history.replaceState({}, "", "/login?next=/account");
    const user = userEvent.setup();
    render(<LoginFlow />);
    await requestCode(user, "+84 901 234 567");
    expect(bodyOf(fn, "/phone/login/request")).toEqual({ phone: "+84901234567" });
    expect(screen.getByText(NEUTRAL)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Mã 6 chữ số"), "12ab3456");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/account"));
    expect(bodyOf(fn, "/phone/login/verify")).toEqual({ phone: "+84901234567", code: "123456" });
  });

  it("asks for six digits before verifying", async () => {
    const fn = setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await requestCode(user);
    await user.type(screen.getByLabelText("Mã 6 chữ số"), "123");
    fireEvent.submit(screen.getByRole("form", { name: "Nhập mã SMS" }));
    expect(await screen.findByText("Mã gồm 6 chữ số")).toBeInTheDocument();
    expect(callsTo(fn, "/phone/login/verify")).toHaveLength(0);
  });

  it("hands over to the MFA step when the account needs a second factor", async () => {
    setup(ON, (url) =>
      url.endsWith("/phone/login/verify")
        ? jsonResponse({ mfa_required: true, mfa_token: "mt", factors: ["totp"] })
        : undefined,
    );
    const user = userEvent.setup();
    render(<LoginFlow />);
    await requestCode(user);
    await user.type(screen.getByLabelText("Mã 6 chữ số"), "123456");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
    expect(await screen.findByRole("heading", { name: "Xác minh danh tính" })).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });

  it("shows the server error for a wrong code and keeps the form", async () => {
    setup(ON, (url) => (url.endsWith("/phone/login/verify") ? jsonResponse({ detail: "Mã không đúng hoặc đã hết hạn" }, 400) : undefined));
    const user = userEvent.setup();
    render(<LoginFlow />);
    await requestCode(user);
    await user.type(screen.getByLabelText("Mã 6 chữ số"), "000000");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
    expect(await screen.findByText("Mã không đúng hoặc đã hết hạn")).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });

  it("shows the rate-limit message on 429 when requesting", async () => {
    setup(ON, (url) => (url.endsWith("/phone/login/request") ? jsonResponse({ detail: "slow" }, 429) : undefined));
    const user = userEvent.setup();
    render(<LoginFlow />);
    await openPhoneTab(user);
    await user.type(screen.getByLabelText("Số điện thoại"), "+84901234567");
    await user.click(screen.getByRole("button", { name: "Gửi mã SMS" }));
    expect(await screen.findByText("Thử quá nhiều lần, hãy thử lại sau")).toBeInTheDocument();
    expect(screen.queryByLabelText("Mã 6 chữ số")).not.toBeInTheDocument();
  });

  it("resends only after the cooldown and lets the user change the number", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fn = setup();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await requestCode(user);
    const resend = screen.getByRole("button", { name: /Gửi lại \(30s\)/ });
    expect(resend).toBeDisabled();
    for (let second = 0; second < 30; second += 1) await act(async () => void (await vi.advanceTimersByTimeAsync(1000)));
    await user.click(screen.getByRole("button", { name: "Gửi lại" }));
    await waitFor(() => expect(callsTo(fn, "/phone/login/request")).toHaveLength(2));
    await user.click(screen.getByRole("button", { name: "Đổi số điện thoại" }));
    expect(screen.getByLabelText("Số điện thoại")).toBeInTheDocument();
  });
});

describe("account phone card", () => {
  const rowFor = async (name: string) => {
    const section = await screen.findByRole("region", { name: "Các cách đăng nhập" });
    return within(section).getAllByRole("listitem").find((li) => li.textContent?.startsWith(`${name}:`))!;
  };

  it("is hidden when phone is disabled", async () => {
    setup(OFF);
    render(<AccountView />);
    await screen.findByRole("region", { name: "Các cách đăng nhập" });
    await waitFor(() => expect(screen.queryByText(/^Số điện thoại:/)).not.toBeInTheDocument());
    expect(screen.queryByText(WARNING)).not.toBeInTheDocument();
  });

  it("shows chưa có with the SIM warning, then adds a number with the password", async () => {
    const fn = setup();
    const user = userEvent.setup();
    render(<AccountView />);
    const row = await rowFor("Số điện thoại");
    expect(row).toHaveTextContent("Số điện thoại: chưa có");
    expect(row).toHaveTextContent(WARNING);
    expect(within(row).queryByRole("button", { name: "Xóa số điện thoại" })).not.toBeInTheDocument();
    await user.type(within(row).getByLabelText("Số điện thoại"), "+84 901 234 567");
    await user.type(within(row).getByLabelText("Nhập lại mật khẩu để xác nhận"), "pw123456");
    await user.click(within(row).getByRole("button", { name: "Thêm số điện thoại" }));
    expect(await within(row).findByText("Chúng tôi đã gửi mã xác minh qua SMS.")).toBeInTheDocument();
    expect(bodyOf(fn, "/auth/me/phone", "POST")).toEqual({ phone: "+84901234567", password: "pw123456" });
    expect(callsTo(fn, "/auth/me")).toHaveLength(2); // initial load + reload
  });

  it("rejects an invalid number locally", async () => {
    const fn = setup();
    const user = userEvent.setup();
    render(<AccountView />);
    const row = await rowFor("Số điện thoại");
    await user.type(within(row).getByLabelText("Số điện thoại"), "12345");
    await user.click(within(row).getByRole("button", { name: "Thêm số điện thoại" }));
    expect(await within(row).findByText(/Số điện thoại không hợp lệ/)).toBeInTheDocument();
    expect(callsTo(fn, "/auth/me/phone", "POST")).toHaveLength(0);
  });

  it("shows the code form right after sending, although the server never reports a pending number", async () => {
    // The server stores a number only once verified: /auth/me keeps returning phone: null after the SMS is sent.
    const fn = setup(ON, undefined, { phone: null, phone_verified: false });
    const user = userEvent.setup();
    render(<AccountView />);
    const row = await rowFor("Số điện thoại");
    expect(within(row).queryByLabelText(/Mã SMS/)).toBeNull();
    await user.type(within(row).getByLabelText("Số điện thoại"), "+84901234567");
    await user.type(within(row).getByLabelText(/Nhập lại mật khẩu/), "Correct-Horse-91!");
    await user.click(within(row).getByRole("button", { name: "Thêm số điện thoại" }));
    await user.type(await within(row).findByLabelText(/Mã SMS/), "123456");
    await user.click(within(row).getByRole("button", { name: "Xác minh số" }));
    expect(await within(row).findByText("Đã xác minh số điện thoại.")).toBeInTheDocument();
    expect(bodyOf(fn, "/auth/me/phone/verify")).toEqual({ code: "123456" });
    expect(within(row).queryByLabelText(/Mã SMS/)).toBeNull();
  });

  it("verifies an unverified number with the SMS code and reloads", async () => {
    const fn = setup(ON, undefined, { phone: "+84•••••567", phone_verified: false });
    const user = userEvent.setup();
    render(<AccountView />);
    const row = await rowFor("Số điện thoại");
    expect(row).toHaveTextContent("+84•••••567 (chưa xác minh)");
    expect(within(row).getByRole("button", { name: "Đổi số điện thoại" })).toBeInTheDocument();
    await user.type(within(row).getByLabelText(/Mã SMS/), "12a3456");
    await user.click(within(row).getByRole("button", { name: "Xác minh số" }));
    expect(await within(row).findByText("Đã xác minh số điện thoại.")).toBeInTheDocument();
    expect(bodyOf(fn, "/auth/me/phone/verify")).toEqual({ code: "123456" });
  });

  it("asks for six digits and surfaces a wrong-code error", async () => {
    setup(ON, (url) => (url.endsWith("/me/phone/verify") ? jsonResponse({ detail: "Mã không đúng" }, 400) : undefined), {
      phone: "+84•••••567",
      phone_verified: false,
    });
    const user = userEvent.setup();
    render(<AccountView />);
    const row = await rowFor("Số điện thoại");
    await user.type(within(row).getByLabelText(/Mã SMS/), "123");
    fireEvent.submit(within(row).getByRole("form", { name: "Xác minh số điện thoại" }));
    expect(await within(row).findByText("Mã gồm 6 chữ số")).toBeInTheDocument();
    await user.type(within(row).getByLabelText(/Mã SMS/), "456");
    await user.click(within(row).getByRole("button", { name: "Xác minh số" }));
    expect(await within(row).findByText("Mã không đúng")).toBeInTheDocument();
  });

  it("shows a verified number and removes it with the password", async () => {
    const fn = setup(ON, undefined, { phone: "+84•••••567", phone_verified: true });
    const user = userEvent.setup();
    render(<AccountView />);
    const row = await rowFor("Số điện thoại");
    expect(row).toHaveTextContent("+84•••••567 (đã xác minh)");
    expect(within(row).queryByLabelText(/Mã SMS/)).not.toBeInTheDocument();
    await user.type(within(row).getByLabelText("Nhập lại mật khẩu để xác nhận"), "pw123456");
    await user.click(within(row).getByRole("button", { name: "Xóa số điện thoại" }));
    expect(await within(row).findByText("Đã xóa số điện thoại.")).toBeInTheDocument();
    expect(bodyOf(fn, "/auth/me/phone", "DELETE")).toEqual({ password: "pw123456" });
  });
});

describe("PhoneMethod without a password (re-authentication)", () => {
  const REAUTH = jsonResponse({ detail: "Re-authentication required", reauth: ["email"] }, 401);

  function server(method: "POST" | "DELETE") {
    let fresh = false;
    const fn = mockFetch((url, init) => {
      if (url.endsWith("/reauth/email/request")) return jsonResponse({});
      if (url.includes("/reauth/email/verify")) {
        fresh = true;
        return jsonResponse({ fresh_until: "2030-01-01T00:00:00Z" });
      }
      if (url.endsWith("/auth/me/phone") && init.method === method) return fresh ? jsonResponse({ ok: true }, 202) : REAUTH.clone();
      return jsonResponse({ detail: "unexpected " + url }, 500);
    });
    return fn;
  }

  async function proveByEmail(user: User) {
    const box = await screen.findByRole("dialog");
    await user.click(within(box).getByRole("button", { name: "Gửi mã qua email" }));
    await user.type(await within(box).findByLabelText("Mã xác minh (6 chữ số)"), "123456");
    await user.click(within(box).getByRole("button", { name: "Xác nhận" }));
  }

  it("adds a number after the re-authentication dialog and sends no password", async () => {
    const fn = server("POST");
    const onDone = vi.fn();
    const user = userEvent.setup();
    render(<PhoneMethod me={{ ...me, has_password: false, phone: null }} onDone={onDone} />);
    expect(screen.queryByLabelText("Nhập lại mật khẩu để xác nhận")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Số điện thoại"), "+84901234567");
    await user.click(screen.getByRole("button", { name: "Thêm số điện thoại" }));
    await proveByEmail(user);
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const posts = callsTo(fn, "/auth/me/phone", "POST");
    expect(posts).toHaveLength(2);
    expect(JSON.parse(String(posts[1][1].body))).toEqual({ phone: "+84901234567" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("removes a number after the re-authentication dialog", async () => {
    const fn = server("DELETE");
    const onDone = vi.fn();
    const user = userEvent.setup();
    render(<PhoneMethod me={{ ...me, has_password: false, phone: "+84•••••567", phone_verified: true }} onDone={onDone} />);
    await user.click(screen.getByRole("button", { name: "Xóa số điện thoại" }));
    await proveByEmail(user);
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(callsTo(fn, "/auth/me/phone", "DELETE")).toHaveLength(2);
  });

  it("keeps everything unchanged when the dialog is cancelled", async () => {
    server("POST");
    const onDone = vi.fn();
    const user = userEvent.setup();
    render(<PhoneMethod me={{ ...me, has_password: false, phone: null }} onDone={onDone} />);
    await user.type(screen.getByLabelText("Số điện thoại"), "+84901234567");
    await user.click(screen.getByRole("button", { name: "Thêm số điện thoại" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Hủy" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(onDone).not.toHaveBeenCalled();
  });
});
