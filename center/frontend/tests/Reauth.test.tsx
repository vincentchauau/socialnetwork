import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, reauthRequired, setCsrfToken } from "@sn/api";
import BiometricMethod from "../app/components/BiometricMethod";
import DeleteAccount from "../app/components/DeleteAccount";
import EmailMethod from "../app/components/EmailMethod";
import LinkGoogle from "../app/components/LinkGoogle";
import PasskeyMethod from "../app/components/PasskeyMethod";
import { REAUTH_CANCELLED } from "../app/components/ReauthDialog";
import TotpMethod from "../app/components/TotpMethod";
import * as auth from "../app/lib/auth";
import { PASSKEY_CANCELLED } from "../app/lib/passkey";
import { jsonResponse, me, mockFetch } from "./helpers";

const goTo = vi.hoisted(() => vi.fn());
vi.mock("../app/lib/navigate", async (original) => ({
  ...(await original<typeof import("../app/lib/navigate")>()),
  goTo,
}));

const webauthn = vi.hoisted(() => ({
  supported: true,
  startAuthentication: vi.fn(),
  startRegistration: vi.fn(),
}));
vi.mock("@simplewebauthn/browser", () => ({
  browserSupportsWebAuthn: () => webauthn.supported,
  startAuthentication: webauthn.startAuthentication,
  startRegistration: webauthn.startRegistration,
}));

vi.mock("../app/components/GoogleSignInButton", () => ({
  default: ({ onCredential, onError }: { onCredential: (t: string) => void; onError: (m: string) => void }) => (
    <>
      <button type="button" onClick={() => onCredential("google-token")}>fake google</button>
      <button type="button" onClick={() => onError("Đăng nhập Google thất bại")}>fake google error</button>
    </>
  ),
}));

const REAUTH = "Re-authentication required";
const reauthBody = (methods: string[]) => jsonResponse({ detail: REAUTH, reauth: methods }, 401);
const FRESH = { fresh_until: "2030-01-01T00:00:00Z" };

type Handler = (url: string, init: RequestInit) => Response | undefined;
type User = ReturnType<typeof userEvent.setup>;

/**
 * A server where `target` demands re-authentication until a reauth endpoint succeeded
 * (every successful reauth call, except the email request, makes the target succeed).
 * `extra` can override any route (it runs first).
 */
function server(target: string, methods: string[], extra?: Handler, method = "DELETE") {
  const state = { fresh: false, targetCalls: 0 };
  const fn = mockFetch((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/config")) return jsonResponse({ google_client_id: "cid", biometrics_enabled: false });
    if (url.endsWith("/reauth/passkey/options")) return jsonResponse({ options: { challenge: "c" }, challenge_token: "ct" });
    if (url.endsWith("/reauth/email/request")) return jsonResponse({});
    if (url.includes("/reauth/")) {
      state.fresh = true;
      return jsonResponse(FRESH);
    }
    if (url.endsWith(target) && (init.method ?? "GET") === method) {
      state.targetCalls += 1;
      return state.fresh ? jsonResponse(target === "/auth/me" ? null : {}, target === "/auth/me" ? 204 : 200) : reauthBody(methods);
    }
    return jsonResponse({ detail: "unexpected " + url }, 500);
  });
  return { fn, state };
}

const callsTo = (fn: ReturnType<typeof mockFetch>, suffix: string) => fn.mock.calls.filter(([url]) => url.endsWith(suffix));
const dialog = () => screen.queryByRole("dialog");

async function startDelete(user: User) {
  const view = render(<DeleteAccount hasPassword={false} />);
  await user.type(screen.getByLabelText("Xác nhận"), "XOA");
  await user.click(screen.getByRole("button", { name: "Xóa tài khoản của tôi" }));
  return { box: await screen.findByRole("dialog"), view };
}

async function emailProof(user: User, box: HTMLElement, code = "123456") {
  await user.click(within(box).getByRole("button", { name: "Gửi mã qua email" }));
  await user.type(await within(box).findByLabelText("Mã xác minh (6 chữ số)"), code);
  await user.click(within(box).getByRole("button", { name: "Xác nhận" }));
}

beforeEach(() => {
  goTo.mockReset();
  webauthn.supported = true;
  webauthn.startAuthentication.mockReset();
  webauthn.startRegistration.mockReset();
  setCsrfToken(null);
  vi.unstubAllGlobals();
});

describe("apiFetch and the reauth 401", () => {
  it("exposes the JSON body and never refreshes or retries a reauth 401", async () => {
    const fn = mockFetch(() => reauthBody(["passkey", "email"]));
    const error = (await apiFetch("/api/center/auth/me/email", { method: "DELETE" }).catch((e) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toBe(REAUTH);
    expect((error as ApiError).body).toEqual({ detail: REAUTH, reauth: ["passkey", "email"] });
    expect(reauthRequired(error)).toEqual(["passkey", "email"]);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("still refreshes on an ordinary 401", async () => {
    let calls = 0;
    const fn = mockFetch((url) => {
      if (url.endsWith("/auth/refresh")) return jsonResponse({});
      calls += 1;
      return calls === 1 ? jsonResponse({ detail: "expired" }, 401) : jsonResponse({ ok: true });
    });
    await expect(apiFetch("/api/center/auth/x")).resolves.toEqual({ ok: true });
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it.each([
    ["a non-ApiError", new Error("x")],
    ["a non-401", new ApiError(403, "no", { reauth: ["email"] })],
    ["a 401 without a list", new ApiError(401, "no", { reauth: "email" })],
    ["a 401 without a body", new ApiError(401, "no")],
  ])("reauthRequired is null for %s", (_name, error) => {
    expect(reauthRequired(error)).toBeNull();
  });

  it("keeps only string methods and handles a non-JSON error body", async () => {
    expect(reauthRequired(new ApiError(401, "x", { reauth: ["email", 3] }))).toEqual(["email"]);
    mockFetch(() => new Response("<html>", { status: 500 }));
    const error = (await apiFetch("/api/center/x").catch((e) => e)) as ApiError;
    expect(error.message).toBe("Request failed (500)");
    expect(error.body).toBeUndefined();
  });
});

describe("reauth helpers", () => {
  it("call the documented endpoints", async () => {
    const fn = mockFetch((url) => (url.endsWith("/methods") ? jsonResponse({ methods: ["email"] }) : jsonResponse(FRESH)));
    expect(await auth.reauthMethods()).toEqual({ methods: ["email"] });
    await auth.reauthGoogle("tok");
    await auth.reauthEmailRequest();
    await auth.reauthEmailVerify(" 123456 ");
    const bodies = fn.mock.calls.map(([url, init]) => [url, init.body]);
    expect(bodies).toContainEqual(["/api/center/auth/reauth/google", JSON.stringify({ id_token: "tok" })]);
    expect(bodies).toContainEqual(["/api/center/auth/reauth/email/request", "{}"]);
    expect(bodies).toContainEqual(["/api/center/auth/reauth/email/verify", JSON.stringify({ code: "123456" })]);
  });

  it("reauthPasskey signs the options and verifies with the challenge token", async () => {
    webauthn.startAuthentication.mockResolvedValue({ id: "cred" });
    const { fn } = server("/x", []);
    await auth.reauthPasskey();
    const verify = callsTo(fn, "/reauth/passkey/verify")[0][1];
    expect(JSON.parse(String(verify.body))).toEqual({ credential: { id: "cred" }, challenge_token: "ct" });
  });
});

describe("ReauthDialog through DeleteAccount (account without a password)", () => {
  it("passkey: proves identity, retries the delete once and closes", async () => {
    webauthn.startAuthentication.mockResolvedValue({ id: "cred" });
    const { fn, state } = server("/auth/me", ["passkey", "google", "email"]);
    const user = userEvent.setup();
    const { box } = await startDelete(user);
    expect(box).toHaveAttribute("aria-modal", "true");
    expect(box).toHaveFocus();
    expect(within(box).getByRole("button", { name: "Gửi mã qua email" })).toBeInTheDocument();
    await user.click(within(box).getByRole("button", { name: "Dùng Passkey" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(dialog()).toBeNull();
    expect(state.targetCalls).toBe(2);
    expect(callsTo(fn, "/reauth/passkey/verify")).toHaveLength(1);
  });

  it("a cancelled passkey ceremony keeps the dialog open; cancel then rejects quietly", async () => {
    webauthn.startAuthentication.mockRejectedValue(Object.assign(new Error("x"), { name: "NotAllowedError" }));
    const { state } = server("/auth/me", ["passkey"]);
    const user = userEvent.setup();
    const { box } = await startDelete(user);
    await user.click(within(box).getByRole("button", { name: "Dùng Passkey" }));
    expect(await within(box).findByText(PASSKEY_CANCELLED)).toBeInTheDocument();
    await user.click(within(box).getByRole("button", { name: "Hủy" }));
    await waitFor(() => expect(dialog()).toBeNull());
    expect(await screen.findByText(REAUTH_CANCELLED)).toBeInTheDocument();
    expect(state.targetCalls).toBe(1);
    expect(goTo).not.toHaveBeenCalled();
  });

  it("shows the server error when the passkey verification is rejected", async () => {
    webauthn.startAuthentication.mockResolvedValue({ id: "cred" });
    server("/auth/me", ["passkey"], (url) => (url.endsWith("/passkey/verify") ? jsonResponse({ detail: "Passkey không hợp lệ" }, 400) : undefined));
    const user = userEvent.setup();
    const { box } = await startDelete(user);
    await user.click(within(box).getByRole("button", { name: "Dùng Passkey" }));
    expect(await within(box).findByText("Passkey không hợp lệ")).toBeInTheDocument();
    expect(dialog()).not.toBeNull();
  });

  it("offers only the listed methods (email) and walks through the code step", async () => {
    const { fn, state } = server("/auth/me", ["email"]);
    const user = userEvent.setup();
    const { box } = await startDelete(user);
    expect(within(box).queryByRole("button", { name: "Dùng Passkey" })).toBeNull();
    expect(within(box).queryByText("Đăng nhập lại bằng Google")).toBeNull();
    await user.click(within(box).getByRole("button", { name: "Gửi mã qua email" }));
    const field = await within(box).findByLabelText("Mã xác minh (6 chữ số)");
    expect(callsTo(fn, "/reauth/email/request")).toHaveLength(1);
    await user.type(field, "12a3");
    expect(field).toHaveValue("123");
    await user.click(within(box).getByRole("button", { name: "Xác nhận" }));
    expect(await within(box).findByText("Mã gồm 6 chữ số")).toBeInTheDocument();
    await user.type(field, "456");
    await user.click(within(box).getByRole("button", { name: "Gửi lại mã" }));
    await waitFor(() => expect(callsTo(fn, "/reauth/email/request")).toHaveLength(2));
    await user.click(within(box).getByRole("button", { name: "Xác nhận" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(JSON.parse(String(callsTo(fn, "/reauth/email/verify")[0][1].body))).toEqual({ code: "123456" });
    expect(state.targetCalls).toBe(2);
  });

  it("email: a failed send and a wrong code show errors and do not retry the action", async () => {
    let sends = 0;
    const { state } = server("/auth/me", ["email"], (url) => {
      if (url.endsWith("/email/verify")) return jsonResponse({ detail: "Mã không đúng" }, 400);
      if (url.endsWith("/email/request")) return ++sends === 1 ? jsonResponse({ detail: "Không gửi được" }, 500) : jsonResponse({});
      return undefined;
    });
    const user = userEvent.setup();
    const { box } = await startDelete(user);
    await user.click(within(box).getByRole("button", { name: "Gửi mã qua email" }));
    expect(await within(box).findByText("Không gửi được")).toBeInTheDocument();
    await emailProof(user, box, "111111");
    expect(await within(box).findByText("Mã không đúng")).toBeInTheDocument();
    expect(state.targetCalls).toBe(1);
  });

  it("google: uses the Google button, then retries", async () => {
    const { fn, state } = server("/auth/me", ["google"]);
    const user = userEvent.setup();
    const { box } = await startDelete(user);
    expect(within(box).queryByRole("button", { name: "Dùng Passkey" })).toBeNull();
    await user.click(await within(box).findByRole("button", { name: "fake google" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(JSON.parse(String(callsTo(fn, "/reauth/google")[0][1].body))).toEqual({ id_token: "google-token" });
    expect(state.targetCalls).toBe(2);
  });

  it("google: shows the error from Google and from the server", async () => {
    server("/auth/me", ["google"], (url) => (url.endsWith("/reauth/google") ? jsonResponse({ detail: "Sai tài khoản Google" }, 403) : undefined));
    const user = userEvent.setup();
    const { box } = await startDelete(user);
    await user.click(await within(box).findByRole("button", { name: "fake google error" }));
    expect(await within(box).findByText("Đăng nhập Google thất bại")).toBeInTheDocument();
    await user.click(within(box).getByRole("button", { name: "fake google" }));
    expect(await within(box).findByText("Sai tài khoản Google")).toBeInTheDocument();
  });

  it.each([
    ["has no client id", () => jsonResponse({ google_client_id: null })],
    ["config fails", () => jsonResponse({ detail: "x" }, 500)],
  ])("google: explains when the config %s", async (_name, config) => {
    server("/auth/me", ["google"], (url) => (url.endsWith("/auth/config") ? config() : undefined));
    const { box } = await startDelete(userEvent.setup());
    expect(await within(box).findByText("Đăng nhập Google chưa được cấu hình.")).toBeInTheDocument();
  });

  it("explains when no usable method is offered and Escape closes the dialog", async () => {
    const { state } = server("/auth/me", ["fingerprint"]);
    const user = userEvent.setup();
    const { box } = await startDelete(user);
    expect(within(box).getByText(/Không có cách xác minh phù hợp/)).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(dialog()).toBeNull());
    expect(await screen.findByText(REAUTH_CANCELLED)).toBeInTheDocument();
    expect(state.targetCalls).toBe(1);
  });

  it("disables the passkey button when the browser has no WebAuthn", async () => {
    webauthn.supported = false;
    server("/auth/me", ["passkey"]);
    const { box } = await startDelete(userEvent.setup());
    expect(within(box).getByRole("button", { name: "Dùng Passkey" })).toBeDisabled();
    expect(within(box).getByText(/không hỗ trợ Passkey/)).toBeInTheDocument();
  });

  it("retries only once: a second reauth 401 is shown as an error without reopening the dialog", async () => {
    webauthn.startAuthentication.mockResolvedValue({ id: "cred" });
    let calls = 0;
    server("/auth/me", ["passkey"], (url, init) => {
      if (url.endsWith("/auth/me") && init.method === "DELETE") {
        calls += 1;
        return reauthBody(["passkey"]);
      }
      return undefined;
    });
    const user = userEvent.setup();
    const { box } = await startDelete(user);
    await user.click(within(box).getByRole("button", { name: "Dùng Passkey" }));
    expect(await screen.findByText(REAUTH)).toBeInTheDocument();
    expect(dialog()).toBeNull();
    expect(calls).toBe(2);
    expect(goTo).not.toHaveBeenCalled();
  });

  it("does not open the dialog for ordinary errors", async () => {
    server("/auth/me", [], (url, init) => (url.endsWith("/auth/me") && init.method === "DELETE" ? jsonResponse({ detail: "Không xóa được" }, 400) : undefined));
    const user = userEvent.setup();
    render(<DeleteAccount hasPassword={false} />);
    await user.type(screen.getByLabelText("Xác nhận"), "XOA");
    await user.click(screen.getByRole("button", { name: "Xóa tài khoản của tôi" }));
    expect(await screen.findByText("Không xóa được")).toBeInTheDocument();
    expect(dialog()).toBeNull();
  });

  it("does not submit the surrounding form when the code form inside the dialog is submitted", async () => {
    const { state } = server("/auth/me", ["email"]);
    const user = userEvent.setup();
    const { box } = await startDelete(user);
    await user.click(within(box).getByRole("button", { name: "Gửi mã qua email" }));
    await user.type(await within(box).findByLabelText("Mã xác minh (6 chữ số)"), "12{Enter}");
    expect(await within(box).findByText("Mã gồm 6 chữ số")).toBeInTheDocument();
    expect(state.targetCalls).toBe(1);
  });

  it("settles a pending dialog quietly when the component unmounts", async () => {
    const { state } = server("/auth/me", ["email"]);
    const { view } = await startDelete(userEvent.setup());
    view.unmount();
    await waitFor(() => expect(dialog()).toBeNull());
    expect(state.targetCalls).toBe(1);
  });

  it("returns focus to the opener after closing", async () => {
    server("/auth/me", ["email"]);
    const user = userEvent.setup();
    render(<DeleteAccount hasPassword={false} />);
    await user.type(screen.getByLabelText("Xác nhận"), "XOA");
    const submit = screen.getByRole("button", { name: "Xóa tài khoản của tôi" });
    submit.focus();
    await user.click(submit);
    const box = await screen.findByRole("dialog");
    await user.click(within(box).getByRole("button", { name: "Hủy" }));
    await waitFor(() => expect(submit).toHaveFocus());
  });
});

describe("accounts with a password are unchanged", () => {
  it("DeleteAccount sends the password and shows plain errors", async () => {
    const fn = mockFetch(() => jsonResponse({ detail: "Mật khẩu không đúng" }, 403));
    const user = userEvent.setup();
    render(<DeleteAccount hasPassword />);
    await user.type(screen.getByLabelText("Xác nhận"), "XOA");
    await user.type(screen.getByLabelText("Nhập lại mật khẩu để xác nhận"), "pw123456");
    await user.click(screen.getByRole("button", { name: "Xóa tài khoản của tôi" }));
    expect(await screen.findByText("Mật khẩu không đúng")).toBeInTheDocument();
    expect(JSON.parse(String(fn.mock.calls[0][1].body))).toEqual({ password: "pw123456" });
    expect(dialog()).toBeNull();
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("EmailMethod still sends the password with the change", async () => {
    const fn = mockFetch(() => jsonResponse({}));
    const onDone = vi.fn();
    const user = userEvent.setup();
    render(<EmailMethod me={{ ...me, email: null }} onDone={onDone} />);
    await user.type(screen.getByLabelText("Địa chỉ email"), "a@b.co");
    await user.type(screen.getByLabelText("Nhập lại mật khẩu để xác nhận"), "pw123456");
    await user.click(screen.getByRole("button", { name: "Thêm email" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(JSON.parse(String(fn.mock.calls[0][1].body))).toEqual({ email: "a@b.co", password: "pw123456" });
    expect(dialog()).toBeNull();
  });
});

describe("integration at the other call sites (no password)", () => {
  it("TotpMethod: starting the setup asks for email proof, then continues to the QR step", async () => {
    const { state } = server(
      "/totp/setup",
      ["email"],
      (url, init) => {
        if (url.endsWith("/totp/setup") && init.method === "POST" && state.fresh) {
          state.targetCalls += 1;
          return jsonResponse({ secret: "SECRET", otpauth_uri: "otpauth://totp/x?secret=SECRET" });
        }
        return undefined;
      },
      "POST",
    );
    const user = userEvent.setup();
    render(<TotpMethod enabled={false} recoveryCodesLeft={0} hasPassword={false} onDone={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Bật" }));
    await emailProof(user, await screen.findByRole("dialog"));
    expect(await screen.findByLabelText("Khóa thiết lập")).toHaveTextContent("SECRET");
    expect(state.targetCalls).toBe(2);
    expect(dialog()).toBeNull();
  });

  it("TotpMethod: disabling asks for proof and retries", async () => {
    const { state } = server("/auth/totp", ["email"], (url, init) => {
      if (url.endsWith("/auth/me") && (init.method ?? "GET") === "GET") return jsonResponse(me);
      return undefined;
    });
    const user = userEvent.setup();
    const onDone = vi.fn();
    render(<TotpMethod enabled recoveryCodesLeft={5} hasPassword={false} onDone={onDone} />);
    await user.click(screen.getByRole("button", { name: "Tắt" }));
    await user.type(screen.getByLabelText("Mã xác thực hoặc mã khôi phục"), "123456");
    await user.click(screen.getByRole("button", { name: "Xác nhận tắt" }));
    await emailProof(user, await screen.findByRole("dialog"), "654321");
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(state.targetCalls).toBe(2);
  });

  it("TotpMethod: regenerating recovery codes and the confirm step are protected too", async () => {
    const { state } = server(
      "/totp/recovery-codes",
      ["email"],
      (url) => (url.endsWith("/totp/recovery-codes") && state.fresh ? (state.targetCalls++, jsonResponse({ recovery_codes: ["aaaa-bbbb"] })) : undefined),
      "POST",
    );
    const user = userEvent.setup();
    render(<TotpMethod enabled recoveryCodesLeft={5} hasPassword={false} onDone={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Tạo lại mã khôi phục" }));
    await user.type(screen.getByLabelText(/Mã xác thực hiện tại/), "123456");
    await user.click(screen.getByRole("button", { name: "Xác nhận tạo lại mã" }));
    await emailProof(user, await screen.findByRole("dialog"));
    expect(await screen.findByText("aaaa-bbbb")).toBeInTheDocument();
  });

  it("TotpMethod: the enable step asks for proof and retries", async () => {
    const { state } = server(
      "/totp/enable",
      ["email"],
      (url, init) => {
        if (url.endsWith("/totp/setup")) return jsonResponse({ secret: "S", otpauth_uri: "otpauth://totp/x?secret=S" });
        if (url.endsWith("/auth/me") && (init.method ?? "GET") === "GET") return jsonResponse(me);
        if (url.endsWith("/totp/enable") && state.fresh) return (state.targetCalls++, jsonResponse({ recovery_codes: ["c1"] }));
        return undefined;
      },
      "POST",
    );
    const user = userEvent.setup();
    render(<TotpMethod enabled={false} recoveryCodesLeft={0} hasPassword={false} onDone={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Bật" }));
    await user.type(await screen.findByLabelText("Mã xác thực 6 chữ số"), "123456");
    await user.click(screen.getByRole("button", { name: "Xác nhận và bật" }));
    await emailProof(user, await screen.findByRole("dialog"), "654321");
    expect(await screen.findByText("c1")).toBeInTheDocument();
    expect(state.targetCalls).toBe(2);
  });

  it("EmailMethod: removing an email asks for passkey proof", async () => {
    webauthn.startAuthentication.mockResolvedValue({ id: "cred" });
    const { state } = server("/auth/me/email", ["passkey"]);
    const onDone = vi.fn();
    const user = userEvent.setup();
    render(<EmailMethod me={{ ...me, has_password: false, email: "a@b.co", email_verified: true }} onDone={onDone} />);
    await user.click(screen.getByRole("button", { name: "Xóa email" }));
    const box = await screen.findByRole("dialog");
    await user.click(within(box).getByRole("button", { name: "Dùng Passkey" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(state.targetCalls).toBe(2);
    expect(await screen.findByText("Đã xóa email.")).toBeInTheDocument();
  });

  it("EmailMethod: resend and change go through the same step-up", async () => {
    const calls = { n: 0 };
    mockFetch((url) => {
      if (url.endsWith("/auth/me/email")) {
        calls.n += 1;
        return jsonResponse({});
      }
      return jsonResponse({}, 500);
    });
    const user = userEvent.setup();
    render(<EmailMethod me={{ ...me, has_password: false, email: "a@b.co", email_verified: false }} onDone={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Gửi lại" }));
    expect(await screen.findByText(/Đã gửi lại mã xác minh/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Email mới"), "n@b.co");
    await user.click(screen.getByRole("button", { name: "Đổi email" }));
    await waitFor(() => expect(calls.n).toBe(2));
  });

  it("EmailMethod: adding an email asks for proof and retries", async () => {
    const { state } = server("/auth/me/email", ["email"], undefined, "POST");
    const onDone = vi.fn();
    const user = userEvent.setup();
    render(<EmailMethod me={{ ...me, has_password: false, email: null }} onDone={onDone} />);
    await user.type(screen.getByLabelText("Địa chỉ email"), "a@b.co");
    await user.click(screen.getByRole("button", { name: "Thêm email" }));
    await emailProof(user, await screen.findByRole("dialog"));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(state.targetCalls).toBe(2);
  });

  const item = { id: 7, name: "Laptop", created_at: "2025-01-01T00:00:00Z", last_used_at: null, backed_up: false, transports: [] };

  it("PasskeyMethod: removing a passkey retries after proof", async () => {
    const { state } = server("/passkeys/7", ["email"]);
    const onDone = vi.fn();
    const user = userEvent.setup();
    render(<PasskeyMethod passkeys={[item]} hasPassword={false} onDone={onDone} />);
    await user.click(screen.getByRole("button", { name: "Xóa" }));
    await user.click(screen.getByRole("button", { name: "Xác nhận xóa" }));
    await emailProof(user, await screen.findByRole("dialog"));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(state.targetCalls).toBe(2);
  });

  it("PasskeyMethod: adding a passkey is protected at the options call", async () => {
    webauthn.startAuthentication.mockResolvedValue({ id: "cred" });
    webauthn.startRegistration.mockResolvedValue({ id: "new" });
    const { state } = server(
      "/me/passkeys/options",
      ["passkey"],
      (url, init) => {
        if (url.endsWith("/me/passkeys/options") && state.fresh) return (state.targetCalls++, jsonResponse({ options: {}, challenge_token: "ct" }));
        if (url.endsWith("/me/passkeys") && init.method === "POST") return jsonResponse({ passkeys: [] });
        return undefined;
      },
      "POST",
    );
    const onDone = vi.fn();
    const user = userEvent.setup();
    render(<PasskeyMethod passkeys={[]} hasPassword={false} onDone={onDone} />);
    await user.click(await screen.findByRole("button", { name: "Thêm Passkey" }));
    const box = await screen.findByRole("dialog");
    await user.click(within(box).getByRole("button", { name: "Dùng Passkey" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(state.targetCalls).toBe(2);
  });

  it("LinkGoogle: linking asks for proof and retries", async () => {
    const { state } = server("/auth/me/google", ["email"], undefined, "POST");
    const onDone = vi.fn();
    const user = userEvent.setup();
    render(<LinkGoogle clientId="cid" hasPassword={false} onDone={onDone} />);
    await user.click(screen.getByRole("button", { name: "fake google" }));
    await emailProof(user, await screen.findByRole("dialog"));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(state.targetCalls).toBe(2);
  });

  it("BiometricMethod: removing the voice asks for proof", async () => {
    const { state } = server("/auth/me/voice", ["email"]);
    const onDone = vi.fn();
    const user = userEvent.setup();
    render(<BiometricMethod kind="voice" enabled hasPassword={false} onDone={onDone} />);
    await user.click(screen.getByRole("button", { name: "Hủy giọng nói" }));
    await emailProof(user, await screen.findByRole("dialog"));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(state.targetCalls).toBe(2);
  });
});
