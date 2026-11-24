import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setCsrfToken } from "@sn/api";
import LoginFlow from "../../app/center/components/LoginFlow";
import { headerOf, jsonResponse, me, mockFetch, session } from "./helpers";

const goTo = vi.hoisted(() => vi.fn());
vi.mock("../../app/center/lib/navigate", async (original) => ({
  ...(await original<typeof import("../../app/center/lib/navigate")>()),
  goTo,
}));

const webauthn = vi.hoisted(() => ({ startAuthentication: vi.fn() }));
vi.mock("@simplewebauthn/browser", () => ({
  browserSupportsWebAuthn: () => true,
  startAuthentication: webauthn.startAuthentication,
  startRegistration: vi.fn(),
}));

const FORM = "Đổi tên đăng nhập";
const PASSWORD = "Nhập lại mật khẩu để xác nhận";
const NAME = "Tên đăng nhập";
const SAVED = "Đã đổi tên đăng nhập.";
const COOLDOWN = "Bạn chỉ có thể đổi tên đăng nhập 30 ngày một lần";
const FUTURE = "2999-05-06T00:00:00Z";

type Extra = (url: string, init: RequestInit) => Response | Promise<Response> | undefined;

function setup(account: Record<string, unknown> = {}, extra?: Extra) {
  const state = { csrf: "csrf-1", name: "ann", canRenameAfter: (account.can_rename_after as string | null) ?? null };
  return mockFetch((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/sessions")) return jsonResponse([]);
    if (url.endsWith("/auth/config")) return jsonResponse({ google_client_id: null, biometrics_enabled: false, email_enabled: false });
    if (url.endsWith("/auth/me") && (init.method ?? "GET") === "GET") {
      return jsonResponse({ ...me, ...account, username: state.name, csrf_token: state.csrf, can_rename_after: state.canRenameAfter });
    }
    if (url.endsWith("/me/username")) {
      state.name = JSON.parse(init.body as string).username;
      state.canRenameAfter = FUTURE;
      state.csrf = "csrf-renamed";
      return jsonResponse({ ...session, username: state.name, csrf_token: "csrf-renamed" });
    }
    if (url.endsWith("/auth/logout")) return jsonResponse(null, 204);
    return jsonResponse({});
  });
}

const renameCalls = (fn: ReturnType<typeof mockFetch>) => fn.mock.calls.filter(([url]) => url.endsWith("/me/username"));
const bodyOf = (fn: ReturnType<typeof mockFetch>) => JSON.parse(renameCalls(fn)[0][1].body as string);

async function openForm() {
  return within(await screen.findByRole("form", { name: FORM }));
}

beforeEach(() => {
  goTo.mockReset();
  webauthn.startAuthentication.mockReset();
  setCsrfToken(null);
});

describe("ChangeUsername", () => {
  it("shows the current name, the note and the hints", async () => {
    setup();
    render(<LoginFlow />);
    const form = await openForm();
    expect(form.getByText("ann")).toBeInTheDocument();
    expect(form.getByText(/Mỗi 30 ngày chỉ đổi được một lần/)).toBeInTheDocument();
    expect(form.getByText("(thường + hoa + số + đặc biệt)")).toBeInTheDocument();
    expect(form.queryByText(/3-32 ký tự/)).not.toBeInTheDocument();
    expect(form.getByPlaceholderText("User@123")).toBeInTheDocument();
    expect(form.queryByText(/Có thể đổi lại từ/)).toBeNull();
  });

  it("renames with a password, stores the csrf token, refreshes the name and uses the token afterwards", async () => {
    const fn = setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    const form = await openForm();
    await user.type(form.getByLabelText(NAME), " bob.2 ");
    await user.type(screen.getByLabelText(PASSWORD), "Secret-123");
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));

    expect(await screen.findByText(SAVED)).toBeInTheDocument();
    expect(bodyOf(fn)).toEqual({ username: "bob.2", password: "Secret-123" });
    await waitFor(() => expect(form.getByText("bob.2")).toBeInTheDocument()); // the current name is refreshed
    expect(form.getByLabelText(NAME)).toHaveValue("");

    await user.click(screen.getByRole("button", { name: "Đăng xuất mọi nơi" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/user"));
    const logout = fn.mock.calls.find(([url]) => url.endsWith("/auth/logout"));
    expect(headerOf(logout?.[1], "X-CSRF-Token")).toBe("csrf-renamed");
  });

  it("renames without a password field on a password-less account", async () => {
    const fn = setup({ has_password: false });
    const user = userEvent.setup();
    render(<LoginFlow />);
    const form = await openForm();
    expect(screen.queryByLabelText(PASSWORD)).toBeNull();
    await user.type(form.getByLabelText(NAME), "carol");
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    expect(await screen.findByText(SAVED)).toBeInTheDocument();
    expect(bodyOf(fn).username).toBe("carol");
    expect(bodyOf(fn).password).toBeUndefined();
  });

  it("asks for step-up proof and retries once", async () => {
    let calls = 0;
    const fn = setup({ has_password: false }, (url) => {
      if (url.endsWith("/reauth/passkey/options")) return jsonResponse({ options: { challenge: "c" }, challenge_token: "ct" });
      if (url.endsWith("/reauth/passkey/verify")) return jsonResponse({ fresh_until: "2030-01-01T00:00:00Z" });
      if (url.endsWith("/me/username") && (calls += 1) === 1) {
        return jsonResponse({ detail: "Re-authentication required", reauth: ["passkey"] }, 401);
      }
      return undefined;
    });
    webauthn.startAuthentication.mockResolvedValue({ id: "cred" });
    const user = userEvent.setup();
    render(<LoginFlow />);
    const form = await openForm();
    await user.type(form.getByLabelText(NAME), "dave");
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    const box = await screen.findByRole("dialog");
    await user.click(within(box).getByRole("button", { name: "Dùng Passkey" }));
    expect(await screen.findByText(SAVED)).toBeInTheDocument();
    expect(renameCalls(fn)).toHaveLength(2);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it.each([
    ["Bad Name", "không được chứa khoảng trắng"],
    ["!!!", "Tên đăng nhập gồm 3-32 ký tự"],
    ["Bad:Name", "Tên đăng nhập gồm 3-32 ký tự"],
  ])("validates the name %j before calling the server", async (name, expected) => {
    const fn = setup();
    const user = userEvent.setup();
    render(<LoginFlow />);
    const form = await openForm();
    await user.type(form.getByLabelText(NAME), name);
    await user.type(screen.getByLabelText(PASSWORD), "Secret-123");
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(expected);
    expect(renameCalls(fn)).toHaveLength(0);
  });

  it.each([
    ["409 taken", 409, "Username already taken", "Tên đăng nhập này đã có người dùng"],
    ["422 validation", 422, "Username is reserved", "Username is reserved"],
    ["429 too many", 429, "Too many attempts", "Thử quá nhiều lần, hãy thử lại sau"],
    ["429 cooldown", 429, "You can change your username once every 30 days", COOLDOWN],
    ["409 cooldown", 409, "Username can be changed again after 2026-11-12", COOLDOWN],
  ])("maps %s to Vietnamese", async (_label, status, detail, text) => {
    setup({}, (url) => (url.endsWith("/me/username") ? jsonResponse({ detail }, status) : undefined));
    const user = userEvent.setup();
    render(<LoginFlow />);
    const form = await openForm();
    await user.type(form.getByLabelText(NAME), "erin");
    await user.type(screen.getByLabelText(PASSWORD), "Secret-123");
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    expect(await form.findByRole("alert")).toHaveTextContent(text);
    expect(form.getByLabelText(NAME)).toHaveValue("erin");
    expect(screen.getByLabelText(PASSWORD)).toHaveValue("");
  });

  it("locks the form while saving", async () => {
    let release: (r: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => (release = resolve));
    const fn = setup({}, (url) => (url.endsWith("/me/username") ? pending : undefined));
    const user = userEvent.setup();
    render(<LoginFlow />);
    const form = await openForm();
    await user.type(form.getByLabelText(NAME), "frank");
    await user.type(screen.getByLabelText(PASSWORD), "Secret-123");
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    expect(await screen.findByRole("button", { name: "Đang xử lý..." })).toBeDisabled();
    expect(form.getByLabelText(NAME)).toBeDisabled();
    release(jsonResponse({ ...session, username: "frank", csrf_token: "c2" }));
    expect(await screen.findByText(SAVED)).toBeInTheDocument();
    expect(renameCalls(fn)).toHaveLength(1);
  });

  it("disables the form until can_rename_after and shows the date", async () => {
    setup({ can_rename_after: FUTURE });
    render(<LoginFlow />);
    const form = await openForm();
    expect(form.getByText(/Có thể đổi lại từ/)).toHaveTextContent(new Date(FUTURE).toLocaleDateString("vi-VN"));
    expect(form.getByLabelText(NAME)).toBeDisabled(); // the whole fieldset is, so Enter cannot submit either
  });

  it.each([
    ["a past date", "2000-01-01T00:00:00Z"],
    ["an invalid date", "not-a-date"],
  ])("stays enabled with %s", async (_label, date) => {
    setup({ can_rename_after: date });
    render(<LoginFlow />);
    const form = await openForm();
    expect(form.queryByText(/Có thể đổi lại từ/)).toBeNull();
    expect(form.getByLabelText(NAME)).toBeEnabled();
  });
});
