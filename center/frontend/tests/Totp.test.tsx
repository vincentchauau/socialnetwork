import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AccountView from "../app/components/AccountView";
import LoginFlow from "../app/components/LoginFlow";
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

vi.mock("../app/components/BiometricCapture", () => ({
  default: ({ onVideo }: { onVideo: (b: Blob) => void }) => (
    <button type="button" onClick={() => onVideo(new Blob(["v"]))}>fake video</button>
  ),
}));

type User = ReturnType<typeof userEvent.setup>;
type Handler = (url: string, init: RequestInit) => Response | undefined;

const bodyOf = (init: RequestInit) => JSON.parse(String(init.body));
const callsTo = (fn: ReturnType<typeof mockFetch>, suffix: string) => fn.mock.calls.filter(([url]) => url.endsWith(suffix));

beforeEach(() => {
  goTo.mockReset();
});

/* ------------------------------ login (MfaStep) ------------------------------ */

function loginSetup(factors: string[] | undefined, extra?: Handler) {
  return mockFetch((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/config")) return jsonResponse({ google_client_id: null, biometrics_enabled: false });
    if (url.endsWith("/auth/login")) return jsonResponse({ mfa_required: true, mfa_token: "tok", ...(factors && { factors }) });
    if (url.endsWith("/login/biometric")) return jsonResponse(session);
    return jsonResponse({ detail: "unexpected " + url }, 500);
  });
}

async function reachMfa(user: User) {
  await user.type(await screen.findByLabelText("Tên đăng nhập"), "ann");
  await user.type(screen.getByLabelText("Mật khẩu", { selector: "input" }), "password1");
  await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
  await screen.findByRole("heading", { name: "Xác minh danh tính" });
}

describe("MfaStep factor picker", () => {
  it("offers both factors, starts on the first and switches between them", async () => {
    loginSetup(["totp", "biometric"]);
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    const tablist = screen.getByRole("tablist", { name: "Chọn cách xác minh" });
    const totpTab = within(tablist).getByRole("tab", { name: "Ứng dụng xác thực" });
    const bioTab = within(tablist).getByRole("tab", { name: "Sinh trắc học" });
    expect(totpTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toContainElement(screen.getByLabelText("Mã xác thực 6 chữ số"));
    await user.click(bioTab);
    expect(bioTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("button", { name: "fake video" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Mã xác thực 6 chữ số")).not.toBeInTheDocument();
    await user.click(totpTab);
    expect(screen.getByLabelText("Mã xác thực 6 chữ số")).toBeInTheDocument();
  });

  it("shows no tabs for a single factor", async () => {
    loginSetup(["totp"]);
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Mã xác thực 6 chữ số")).toBeInTheDocument();
  });

  it("treats missing factors (old server) as biometric only and still completes with the clip", async () => {
    const fn = loginSetup(undefined);
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "fake video" }));
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(callsTo(fn, "/login/biometric")).toHaveLength(1);
  });

  it("goes back to the sign-in form on Hủy from the authenticator form", async () => {
    loginSetup(["totp"]);
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    await user.click(screen.getByRole("button", { name: "Hủy" }));
    expect(await screen.findByRole("heading", { name: "Đăng nhập" })).toBeInTheDocument();
  });
});

describe("MfaStep authenticator code", () => {
  const totpRoute = (response: () => Response): Handler => (url) => (url.endsWith("/login/totp") ? response() : undefined);

  it("has an auto-focused numeric one-time-code field that keeps digits only and caps at 6", async () => {
    loginSetup(["totp"]);
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    const field = screen.getByLabelText("Mã xác thực 6 chữ số");
    expect(field).toHaveFocus();
    expect(field).toHaveAttribute("inputmode", "numeric");
    expect(field).toHaveAttribute("autocomplete", "one-time-code");
    expect(field).toHaveAttribute("maxlength", "6");
    await user.type(field, "12a3-45678");
    expect(field).toHaveValue("123456");
  });

  it("keeps the submit disabled until 6 digits, then signs in and redirects", async () => {
    const fn = loginSetup(["totp"], totpRoute(() => jsonResponse(session)));
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    const submit = screen.getByRole("button", { name: "Xác minh và đăng nhập" });
    await user.type(screen.getByLabelText("Mã xác thực 6 chữ số"), "12345");
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText("Mã xác thực 6 chữ số"), "6");
    await user.click(submit);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(bodyOf(callsTo(fn, "/login/totp")[0][1])).toEqual({ mfa_token: "tok", code: "123456" });
  });

  it("locks the form while the request is pending", async () => {
    let release: (response: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => (release = resolve));
    const fn = loginSetup(["totp"]);
    const base = fn.getMockImplementation()!;
    fn.mockImplementation((url, init) => (url.endsWith("/login/totp") ? pending : base(url, init)));
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    await user.type(screen.getByLabelText("Mã xác thực 6 chữ số"), "123456");
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    expect(await screen.findByRole("button", { name: "Đang xử lý..." })).toBeDisabled();
    expect(screen.getByLabelText("Mã xác thực 6 chữ số")).toBeDisabled();
    release(jsonResponse(session));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
  });

  it("shows the wrong-code text on 401 and clears the field", async () => {
    loginSetup(["totp"], totpRoute(() => jsonResponse({ detail: "Invalid code" }, 401)));
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    await user.type(screen.getByLabelText("Mã xác thực 6 chữ số"), "000000");
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Mã không đúng hoặc đã dùng");
    expect(screen.getByLabelText("Mã xác thực 6 chữ số")).toHaveValue("");
    expect(goTo).not.toHaveBeenCalled();
  });

  it("shows the throttling text on 429", async () => {
    loginSetup(["totp"], totpRoute(() => jsonResponse({ detail: "Too many attempts" }, 429)));
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    await user.type(screen.getByLabelText("Mã xác thực 6 chữ số"), "000000");
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Thử quá nhiều lần, hãy đợi rồi thử lại");
  });

  it("falls back to the generic message for other failures", async () => {
    loginSetup(["totp"], totpRoute(() => jsonResponse({ detail: "boom" }, 500)));
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    await user.type(screen.getByLabelText("Mã xác thực 6 chữ số"), "000000");
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});

describe("MfaStep recovery code", () => {
  it("switches to a text field, sends the trimmed lowercase code, and can switch back", async () => {
    const fn = loginSetup(["totp"], (url) => (url.endsWith("/login/totp") ? jsonResponse(session) : undefined));
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    await user.click(screen.getByRole("button", { name: "Dùng mã khôi phục" }));
    const field = screen.getByLabelText("Mã khôi phục");
    expect(field).toHaveFocus();
    expect(field).not.toHaveAttribute("maxlength");
    await user.click(screen.getByRole("button", { name: "Dùng mã từ ứng dụng xác thực" }));
    expect(screen.getByLabelText("Mã xác thực 6 chữ số")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Dùng mã khôi phục" }));
    await user.type(screen.getByLabelText("Mã khôi phục"), "  ABCD-1234  ");
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(bodyOf(callsTo(fn, "/login/totp")[0][1])).toEqual({ mfa_token: "tok", recovery_code: "abcd-1234" });
  });

  it("does not submit an empty recovery code and reports a used one", async () => {
    loginSetup(["totp"], (url) => (url.endsWith("/login/totp") ? jsonResponse({ detail: "Invalid code" }, 401) : undefined));
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    await user.click(screen.getByRole("button", { name: "Dùng mã khôi phục" }));
    expect(screen.getByRole("button", { name: "Xác minh và đăng nhập" })).toBeDisabled();
    await user.type(screen.getByLabelText("Mã khôi phục"), "used-code");
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Mã không đúng hoặc đã dùng");
  });

  it("clears an earlier error when switching mode", async () => {
    loginSetup(["totp"], (url) => (url.endsWith("/login/totp") ? jsonResponse({ detail: "Invalid code" }, 401) : undefined));
    const user = userEvent.setup();
    render(<LoginFlow />);
    await reachMfa(user);
    await user.type(screen.getByLabelText("Mã xác thực 6 chữ số"), "000000");
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    await screen.findByText("Mã không đúng hoặc đã dùng");
    await user.click(screen.getByRole("button", { name: "Dùng mã khôi phục" }));
    expect(screen.queryByText("Mã không đúng hoặc đã dùng")).toBeNull();
  });
});

/* ------------------------------ account card ------------------------------ */

// userEvent.setup() installs its own clipboard stub, so ours goes in afterwards.
function newUser(): User {
  const user = userEvent.setup();
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  return user;
}

const CODES = Array.from({ length: 10 }, (_, index) => `code-${index}`);
const SETUP = { secret: "JBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/Center:ann?secret=JBSWY3DPEHPK3PXP&issuer=Center" };
const writeText = vi.fn();
const createObjectURL = vi.fn(() => "blob:codes");
const revokeObjectURL = vi.fn();

beforeEach(() => {
  writeText.mockReset().mockResolvedValue(undefined);
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
  Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
  Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
});

function accountSetup(account: Partial<typeof me> = {}, extra?: Handler) {
  const state = { current: { ...me, ...account } };
  const fn = mockFetch((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/config")) return jsonResponse({ google_client_id: null, biometrics_enabled: false });
    if (url.endsWith("/auth/me") && (init.method ?? "GET") === "GET") return jsonResponse(state.current);
    if (url.endsWith("/totp/setup")) return jsonResponse(SETUP);
    if (url.endsWith("/totp/enable")) {
      state.current = { ...state.current, totp_enabled: true, recovery_codes_left: 10 };
      return jsonResponse({ recovery_codes: CODES });
    }
    if (url.endsWith("/totp/recovery-codes")) return jsonResponse({ recovery_codes: CODES });
    if (url.endsWith("/auth/totp") && init.method === "DELETE") {
      state.current = { ...state.current, totp_enabled: false, recovery_codes_left: 0 };
      return jsonResponse(null, 204);
    }
    return jsonResponse({ detail: "unexpected " + url }, 500);
  });
  return fn;
}

const card = () => screen.findByRole("region", { name: "Xác thực hai bước (TOTP)" });

async function startSetup(user: User, password = "pw-123456") {
  const region = await card();
  await user.type(within(region).getByLabelText("Nhập lại mật khẩu để xác nhận"), password);
  await user.click(within(region).getByRole("button", { name: "Bật" }));
  await screen.findByRole("img", { name: /Mã QR/ });
}

async function enableTotp(user: User) {
  await startSetup(user);
  await user.type(screen.getByLabelText("Mã xác thực 6 chữ số"), "123456");
  await user.click(screen.getByRole("button", { name: "Xác nhận và bật" }));
  await screen.findByRole("region", { name: "Mã khôi phục" });
}

describe("TOTP card: off", () => {
  it("shows the off state with the second-step hint and a Bật button", async () => {
    accountSetup();
    render(<AccountView />);
    const region = await card();
    expect(region).toHaveTextContent("đang TẮT");
    expect(region).toHaveTextContent("Mã này chỉ dùng làm bước thứ hai sau khi đăng nhập");
    expect(within(region).getByRole("button", { name: "Bật" })).toBeInTheDocument();
  });

  it("asks for the password (when the account has one) and reports a failed setup", async () => {
    accountSetup({}, (url) => (url.endsWith("/totp/setup") ? jsonResponse({ detail: "Wrong password" }, 403) : undefined));
    const user = newUser();
    render(<AccountView />);
    const region = await card();
    await user.type(within(region).getByLabelText("Nhập lại mật khẩu để xác nhận"), "bad");
    await user.click(within(region).getByRole("button", { name: "Bật" }));
    expect(await within(region).findByRole("alert")).toHaveTextContent("Wrong password");
    expect(within(region).getByLabelText("Nhập lại mật khẩu để xác nhận")).toHaveValue("");
  });

  it("skips the password field for an account without a password", async () => {
    const fn = accountSetup({ has_password: false });
    const user = newUser();
    render(<AccountView />);
    const region = await card();
    expect(within(region).queryByLabelText("Nhập lại mật khẩu để xác nhận")).not.toBeInTheDocument();
    await user.click(within(region).getByRole("button", { name: "Bật" }));
    await screen.findByRole("img", { name: /Mã QR/ });
    expect(bodyOf(callsTo(fn, "/totp/setup")[0][1])).toEqual({});
    await user.type(screen.getByLabelText("Mã xác thực 6 chữ số"), "123456");
    await user.click(screen.getByRole("button", { name: "Xác nhận và bật" }));
    await screen.findByRole("region", { name: "Mã khôi phục" });
    expect(bodyOf(callsTo(fn, "/totp/enable")[0][1])).toEqual({ code: "123456" });
  });

  it("renders the QR locally as an inline data URL plus the secret with a copy button", async () => {
    const fn = accountSetup();
    const user = newUser();
    render(<AccountView />);
    await startSetup(user);
    const qr = screen.getByRole("img", { name: /Mã QR/ });
    expect(qr.getAttribute("src")).toMatch(/^data:image\/svg\+xml/);
    // only the gateway is ever called: the secret never reaches a third party
    expect(fn.mock.calls.every(([url]) => url.startsWith("/api/center/"))).toBe(true);
    expect(bodyOf(callsTo(fn, "/totp/setup")[0][1])).toEqual({ password: "pw-123456" });
    expect(screen.getByLabelText("Khóa thiết lập")).toHaveTextContent(SETUP.secret);
    await user.click(screen.getByRole("button", { name: "Sao chép khóa" }));
    expect(writeText).toHaveBeenCalledWith(SETUP.secret);
    expect(await screen.findByText("Đã sao chép")).toBeInTheDocument();
  });

  it("tells the user to copy by hand when the clipboard is refused", async () => {
    accountSetup();
    writeText.mockRejectedValue(new Error("denied"));
    const user = newUser();
    render(<AccountView />);
    await startSetup(user);
    await user.click(screen.getByRole("button", { name: "Sao chép khóa" }));
    expect(await screen.findByText("Không sao chép được, hãy chọn và sao chép thủ công")).toBeInTheDocument();
  });

  it("explains when the QR cannot be drawn", async () => {
    accountSetup({}, (url) =>
      url.endsWith("/totp/setup") ? jsonResponse({ secret: "S", otpauth_uri: "x".repeat(8000) }) : undefined,
    );
    const user = newUser();
    render(<AccountView />);
    const region = await card();
    await user.type(within(region).getByLabelText("Nhập lại mật khẩu để xác nhận"), "pw-123456");
    await user.click(within(region).getByRole("button", { name: "Bật" }));
    expect(await screen.findByText(/Không tạo được mã QR/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Mã QR/ })).not.toBeInTheDocument();
  });

  it("cancels the setup back to the Bật form", async () => {
    accountSetup();
    const user = newUser();
    render(<AccountView />);
    await startSetup(user);
    await user.click(screen.getByRole("button", { name: "Hủy" }));
    expect(screen.getByRole("button", { name: "Bật" })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Mã QR/ })).not.toBeInTheDocument();
  });

  it("keeps the confirm button disabled until 6 digits and shows a wrong-code error", async () => {
    accountSetup({}, (url) => (url.endsWith("/totp/enable") ? jsonResponse({ detail: "Invalid code" }, 401) : undefined));
    const user = newUser();
    render(<AccountView />);
    await startSetup(user);
    const confirm = screen.getByRole("button", { name: "Xác nhận và bật" });
    const field = screen.getByLabelText("Mã xác thực 6 chữ số");
    expect(field).toHaveAttribute("inputmode", "numeric");
    expect(field).toHaveAttribute("autocomplete", "one-time-code");
    await user.type(field, "12x34");
    expect(field).toHaveValue("1234");
    expect(confirm).toBeDisabled();
    await user.type(field, "56");
    await user.click(confirm);
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid code");
    expect(field).toHaveValue("");
  });
});

describe("TOTP card: recovery codes box", () => {
  it("shows the 10 codes once and gates dismissal behind the checkbox", async () => {
    const fn = accountSetup();
    const user = newUser();
    render(<AccountView />);
    await enableTotp(user);
    expect(bodyOf(callsTo(fn, "/totp/enable")[0][1])).toEqual({ code: "123456", password: "pw-123456" });
    const box = screen.getByRole("region", { name: "Mã khôi phục" });
    expect(within(within(box).getByRole("list", { name: "Danh sách mã khôi phục" })).getAllByRole("listitem")).toHaveLength(10);
    const done = within(box).getByRole("button", { name: "Hoàn tất" });
    expect(done).toBeDisabled();
    const saved = within(box).getByRole("checkbox", { name: "Tôi đã lưu các mã này" });
    await user.click(saved);
    expect(done).toBeEnabled();
    await user.click(saved);
    expect(done).toBeDisabled();
    await user.click(saved);
    await user.click(done);
    expect(screen.queryByRole("region", { name: "Mã khôi phục" })).not.toBeInTheDocument();
    // the codes are gone for good: the card now only shows the remaining count
    expect(screen.queryByText("code-0")).not.toBeInTheDocument();
    expect(await screen.findByText(/Còn 10 mã khôi phục/)).toBeInTheDocument();
  });

  it("copies all codes and downloads them as a .txt file", async () => {
    accountSetup();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const user = newUser();
    render(<AccountView />);
    await enableTotp(user);
    const box = screen.getByRole("region", { name: "Mã khôi phục" });
    await user.click(within(box).getByRole("button", { name: "Sao chép" }));
    expect(writeText).toHaveBeenCalledWith(CODES.join("\n"));
    await user.click(within(box).getByRole("button", { name: "Tải xuống (.txt)" }));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const blob = (createObjectURL.mock.calls[0] as unknown as [Blob])[0];
    expect(await blob.text()).toBe(`${CODES.join("\n")}\n`);
    expect(click).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:codes");
    click.mockRestore();
  });
});

describe("TOTP card: on", () => {
  it("shows the remaining count without a warning when plenty are left", async () => {
    accountSetup({ totp_enabled: true, recovery_codes_left: 7 });
    render(<AccountView />);
    const region = await card();
    expect(region).toHaveTextContent("Còn 7 mã khôi phục");
    expect(within(region).queryByRole("alert")).not.toBeInTheDocument();
    expect(within(region).queryByRole("button", { name: "Bật" })).not.toBeInTheDocument();
  });

  it.each([2, 0])("warns when only %i recovery codes are left", async (left) => {
    accountSetup({ totp_enabled: true, recovery_codes_left: left });
    render(<AccountView />);
    const region = await card();
    expect(within(region).getByRole("alert")).toHaveTextContent(`Còn ${left} mã khôi phục`);
  });

  it("regenerates the codes after asking for a current code and shows the box again", async () => {
    const fn = accountSetup({ totp_enabled: true, recovery_codes_left: 1 });
    const user = newUser();
    render(<AccountView />);
    const region = await card();
    await user.click(within(region).getByRole("button", { name: "Tạo lại mã khôi phục" }));
    await user.type(screen.getByLabelText(/Mã xác thực hiện tại/), "123456");
    await user.type(within(region).getByLabelText("Nhập lại mật khẩu để xác nhận"), "pw-123456");
    await user.click(screen.getByRole("button", { name: "Xác nhận tạo lại mã" }));
    expect(await screen.findByRole("region", { name: "Mã khôi phục" })).toBeInTheDocument();
    expect(bodyOf(callsTo(fn, "/totp/recovery-codes")[0][1])).toEqual({ code: "123456", password: "pw-123456" });
  });

  it("rejects an empty code locally and shows a server error for a wrong one, then cancels", async () => {
    const fn = accountSetup({ totp_enabled: true, recovery_codes_left: 5 }, (url) =>
      url.endsWith("/totp/recovery-codes") ? jsonResponse({ detail: "Invalid code" }, 401) : undefined,
    );
    const user = newUser();
    render(<AccountView />);
    const region = await card();
    await user.click(within(region).getByRole("button", { name: "Tạo lại mã khôi phục" }));
    await user.type(within(region).getByLabelText("Nhập lại mật khẩu để xác nhận"), "pw");
    await user.click(screen.getByRole("button", { name: "Xác nhận tạo lại mã" }));
    expect(await screen.findByText("Hãy nhập mã")).toBeInTheDocument();
    expect(callsTo(fn, "/totp/recovery-codes")).toHaveLength(0);
    await user.type(screen.getByLabelText(/Mã xác thực hiện tại/), "000000");
    await user.click(screen.getByRole("button", { name: "Xác nhận tạo lại mã" }));
    expect(await within(region).findByText("Invalid code")).toBeInTheDocument();
    expect(screen.getByLabelText(/Mã xác thực hiện tại/)).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Hủy" }));
    expect(within(region).getByRole("button", { name: "Tắt" })).toBeInTheDocument();
  });

  it("disables TOTP with a recovery code (trimmed, lowercase) and goes back to the off state", async () => {
    const fn = accountSetup({ totp_enabled: true, recovery_codes_left: 5 });
    const user = newUser();
    render(<AccountView />);
    const region = await card();
    await user.click(within(region).getByRole("button", { name: "Tắt" }));
    await user.type(screen.getByLabelText("Mã xác thực hoặc mã khôi phục"), "  ABCD-1234 ");
    await user.type(within(region).getByLabelText("Nhập lại mật khẩu để xác nhận"), "pw-123456");
    await user.click(screen.getByRole("button", { name: "Xác nhận tắt" }));
    expect(await within(region).findByRole("button", { name: "Bật" })).toBeInTheDocument();
    expect(bodyOf(callsTo(fn, "/auth/totp")[0][1])).toEqual({ code: "abcd-1234", password: "pw-123456" });
    expect(region).toHaveTextContent("đang TẮT");
  });

  it("sends no password for an account without one", async () => {
    const fn = accountSetup({ totp_enabled: true, recovery_codes_left: 5, has_password: false });
    const user = newUser();
    render(<AccountView />);
    const region = await card();
    await user.click(within(region).getByRole("button", { name: "Tắt" }));
    expect(within(region).queryByLabelText("Nhập lại mật khẩu để xác nhận")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Mã xác thực hoặc mã khôi phục"), "123456");
    await user.click(screen.getByRole("button", { name: "Xác nhận tắt" }));
    await within(region).findByRole("button", { name: "Bật" });
    expect(bodyOf(callsTo(fn, "/auth/totp")[0][1])).toEqual({ code: "123456" });
  });
});
