import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginFlow from "../../app/center/components/LoginFlow";
import { PasskeyItem, addPasskey, deletePasskey, loginWithPasskey, myPasskeyOptions, passkeyLoginOptions, passkeyRegisterOptions, registerCombined, renamePasskey, takeNewUsername } from "../../app/center/lib/auth";
import { PASSKEY_CANCELLED, PASSKEY_DUPLICATE_DEVICE, PASSKEY_UNSUPPORTED, createPasskeyCredential, getPasskeyCredential } from "../../app/center/lib/passkey";
import { jsonResponse, me, mockFetch, session } from "./helpers";
import { selectTab } from "./tabs";

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

const CONFIG = { google_client_id: null, biometrics_enabled: false };
const CHALLENGE = { options: { challenge: "c" }, challenge_token: "tok" };
const CREDENTIAL = { id: "cred-1", type: "public-key" };

const domError = (name: string) => Object.assign(new Error(name), { name });

type Handler = (url: string, init: RequestInit) => Response | undefined;
const bodyOf = (init: RequestInit | undefined) => JSON.parse(String(init?.body));
const callsTo = (fetchMock: ReturnType<typeof mockFetch>, suffix: string, method?: string) =>
  fetchMock.mock.calls.filter(([url, init]) => url.endsWith(suffix) && (!method || init?.method === method));

beforeEach(() => {
  goTo.mockReset();
  webauthn.supported = true;
  webauthn.start.mockReset();
  webauthn.create.mockReset();
  window.sessionStorage.clear();
  window.history.pushState({}, "", "/user");
});

function loginSetup(extra?: Handler) {
  return mockFetch((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/config")) return jsonResponse(CONFIG);
    if (url.endsWith("/auth/passkey/options")) return jsonResponse(CHALLENGE);
    if (url.endsWith("/auth/passkey/login")) return jsonResponse(session);
    if (url.endsWith("/register/passkey/options")) return jsonResponse(CHALLENGE);
    if (url.endsWith("/register/combined")) return jsonResponse(session, 201);
    return jsonResponse({ detail: "unexpected " + url }, 500);
  });
}

async function openPasskeyTab() {
  const user = userEvent.setup();
  render(<LoginFlow />);
  await selectTab(user, "Passkey");
  return user;
}

describe("Passkey sign-in tab", () => {
  it("explains the method, needs no username and signs in", async () => {
    webauthn.start.mockResolvedValue(CREDENTIAL);
    window.history.pushState({}, "", "/user?next=/user");
    const fetchMock = loginSetup();
    const user = await openPasskeyTab();
    expect(screen.getByText(/Dùng vân tay, Face ID, Windows Hello hoặc khóa bảo mật của thiết bị\. Không cần nhập tên đăng nhập\./)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Tên đăng nhập/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Đăng nhập bằng Passkey" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/user"));
    expect(webauthn.start).toHaveBeenCalledWith({ optionsJSON: CHALLENGE.options });
    expect(bodyOf(callsTo(fetchMock, "/auth/passkey/login")[0][1])).toEqual({ credential: CREDENTIAL, challenge_token: "tok" });
  });

  it("keeps Mật khẩu as the default tab", async () => {
    loginSetup();
    render(<LoginFlow />);
    expect(await screen.findByRole("link", { name: "Mật khẩu" })).toHaveAttribute("aria-current", "page");
  });

  it("maps a cancelled prompt to a friendly message and unlocks the form", async () => {
    webauthn.start.mockRejectedValue(domError("NotAllowedError"));
    const fetchMock = loginSetup();
    const user = await openPasskeyTab();
    await user.click(screen.getByRole("button", { name: "Đăng nhập bằng Passkey" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(PASSKEY_CANCELLED);
    expect(screen.getByRole("button", { name: "Đăng nhập bằng Passkey" })).toBeEnabled();
    expect(callsTo(fetchMock, "/auth/passkey/login")).toHaveLength(0);
    expect(goTo).not.toHaveBeenCalled();
  });

  it("treats AbortError like a cancel", async () => {
    webauthn.start.mockRejectedValue(domError("AbortError"));
    loginSetup();
    const user = await openPasskeyTab();
    await user.click(screen.getByRole("button", { name: "Đăng nhập bằng Passkey" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(PASSKEY_CANCELLED);
  });

  it("shows the server 401 text", async () => {
    webauthn.start.mockResolvedValue(CREDENTIAL);
    loginSetup((url) => (url.endsWith("/auth/passkey/login") ? jsonResponse({ detail: "Passkey sign-in failed" }, 401) : undefined));
    const user = await openPasskeyTab();
    await user.click(screen.getByRole("button", { name: "Đăng nhập bằng Passkey" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Passkey sign-in failed");
    expect(screen.getByRole("button", { name: "Đăng nhập bằng Passkey" })).toBeEnabled();
  });

  it("reports an options failure (throttled)", async () => {
    loginSetup((url) => (url.endsWith("/auth/passkey/options") ? jsonResponse({ detail: "slow" }, 429) : undefined));
    const user = await openPasskeyTab();
    await user.click(screen.getByRole("button", { name: "Đăng nhập bằng Passkey" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Thử quá nhiều lần");
  });

  it("disables the button with a message when the browser has no WebAuthn", async () => {
    webauthn.supported = false;
    loginSetup();
    await openPasskeyTab();
    expect(screen.getByRole("button", { name: "Đăng nhập bằng Passkey" })).toBeDisabled();
    expect(screen.getByRole("note")).toHaveTextContent(PASSKEY_UNSUPPORTED);
    expect(webauthn.start).not.toHaveBeenCalled();
  });
});

describe("Passkey in the register form", () => {
  async function openRegister(extra?: Handler) {
    const fetchMock = loginSetup(extra);
    const user = userEvent.setup();
    render(<LoginFlow />);
    await screen.findByLabelText("Tên đăng nhập");
    await user.click(screen.getByRole("tab", { name: "Đăng ký" }));
    return { fetchMock, user };
  }
  const field = () => screen.getByLabelText(/^Tên đăng nhập/);
  const passwordInput = () => screen.getByLabelText("Mật khẩu", { selector: "input[type=password]" });
  // Passkey has nothing to fill: it counts while its tab is the open one when "Đăng ký" is pressed.
  const openPasskeyTab = (user: ReturnType<typeof userEvent.setup>) => selectTab(user, "Passkey");

  it("creates the passkey first, then sends both fields in the combined payload", async () => {
    webauthn.create.mockResolvedValue(CREDENTIAL);
    const generated = { ...session, username: "user-1a2b3c" };
    const { fetchMock, user } = await openRegister((url) => (url.endsWith("/register/combined") ? jsonResponse(generated, 201) : undefined));
    await openPasskeyTab(user);
    expect(screen.getByText(/Sẽ đăng ký bằng: Passkey/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const optionsCall = callsTo(fetchMock, "/register/passkey/options")[0];
    expect(bodyOf(optionsCall[1])).toEqual({});
    expect(webauthn.create).toHaveBeenCalledWith({ optionsJSON: CHALLENGE.options });
    const form = callsTo(fetchMock, "/register/combined")[0][1].body as FormData;
    expect([...form.keys()]).toEqual(["passkey_credential", "passkey_challenge_token"]);
    expect(JSON.parse(String(form.get("passkey_credential")))).toEqual(CREDENTIAL);
    expect(form.get("passkey_challenge_token")).toBe("tok");
    expect(takeNewUsername()).toBe("user-1a2b3c");
  });

  it("sends the username to the options call and the payload together with a password", async () => {
    webauthn.create.mockResolvedValue(CREDENTIAL);
    const { fetchMock, user } = await openRegister();
    await user.type(field(), "ann");
    await user.type(passwordInput(), "Secret-12345!");
    await openPasskeyTab(user);
    expect(screen.getByText(/Sẽ đăng ký bằng: Mật khẩu, Passkey/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    await waitFor(() => expect(goTo).toHaveBeenCalled());
    expect(bodyOf(callsTo(fetchMock, "/register/passkey/options")[0][1])).toEqual({ username: "ann" });
    const form = callsTo(fetchMock, "/register/combined")[0][1].body as FormData;
    expect(form.get("username")).toBe("ann");
    expect(form.get("password")).toBe("Secret-12345!");
    expect(form.has("passkey_credential")).toBe(true);
  });

  it("does not create a passkey when another tab is open", async () => {
    const { fetchMock, user } = await openRegister();
    await user.type(field(), "ann");
    await user.type(passwordInput(), "Secret-12345!");
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    await waitFor(() => expect(goTo).toHaveBeenCalled());
    expect(webauthn.create).not.toHaveBeenCalled();
    expect(callsTo(fetchMock, "/register/passkey/options")).toHaveLength(0);
  });

  it("keeps the form and shows a friendly message when the prompt is cancelled", async () => {
    webauthn.create.mockRejectedValue(domError("NotAllowedError"));
    const { fetchMock, user } = await openRegister();
    await openPasskeyTab(user);
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(PASSKEY_CANCELLED);
    expect(screen.getByRole("button", { name: "Đăng ký" })).toBeEnabled();
    expect(callsTo(fetchMock, "/register/combined")).toHaveLength(0);
    expect(goTo).not.toHaveBeenCalled();
  });

  it("makes the username optional until a password is typed", async () => {
    const { user } = await openRegister();
    expect(field()).not.toBeRequired(); // nothing typed, or passkey only
    await openPasskeyTab(user);
    expect(field()).not.toBeRequired();
    expect(field()).toHaveAttribute("aria-required", "false");
    expect(screen.getByText(/Google, Giọng nói, Webcam hoặc Passkey/)).toBeInTheDocument();
    await selectTab(user, "Mật khẩu");
    await user.type(passwordInput(), "x");
    expect(field()).toBeRequired(); // password (with or without a passkey)
  });

  it("requires a username when a password is typed even with a passkey", async () => {
    const { fetchMock, user } = await openRegister();
    await user.type(passwordInput(), "Secret-12345!");
    await openPasskeyTab(user);
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    // The missing username blocks the submit before any ceremony starts.
    expect(await screen.findByRole("alert")).toHaveTextContent("Hãy nhập tên đăng nhập");
    expect(webauthn.create).not.toHaveBeenCalled();
    expect(callsTo(fetchMock, "/register/passkey/options")).toHaveLength(0);
  });

  it("explains that the browser has no WebAuthn and does not start a ceremony", async () => {
    webauthn.supported = false;
    const { fetchMock, user } = await openRegister();
    await openPasskeyTab(user);
    expect(screen.getByRole("note")).toHaveTextContent(PASSKEY_UNSUPPORTED);
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(PASSKEY_UNSUPPORTED);
    expect(callsTo(fetchMock, "/register/passkey/options")).toHaveLength(0);
  });
});

const PASSKEYS: PasskeyItem[] = [
  { id: 7, name: "Laptop", created_at: "2026-01-02T03:04:05Z", last_used_at: null, backed_up: false, transports: ["internal"] },
  { id: 8, name: "Điện thoại", created_at: "2026-02-03T00:00:00Z", last_used_at: "2026-03-04T00:00:00Z", backed_up: true, transports: [] },
];

function accountSetup(account: Partial<typeof me> = {}, extra?: Handler) {
  const state = { ...me, ...account };
  return mockFetch((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/config")) return jsonResponse(CONFIG);
    if (url.endsWith("/auth/me") && (init.method ?? "GET") === "GET") {
      return jsonResponse({ ...state, passkey_count: state.passkeys.length });
    }
    return jsonResponse({ detail: "unexpected " + url }, 500);
  });
}

const card = () => screen.findByRole("region", { name: "Passkey" });

describe("Passkey row on /account", () => {
  beforeEach(() => {
    window.location.hash = "#cach-passkey"; // the account page opens on this tab
  });

  it("shows the empty state", async () => {
    accountSetup();
    render(<LoginFlow />);
    expect(await card()).toHaveTextContent("Passkey: chưa có");
    expect(screen.queryByRole("list", { name: "Passkey đã đăng ký" })).not.toBeInTheDocument();
  });

  it("lists each passkey with dates, last use and the synced marker", async () => {
    accountSetup({ passkeys: PASSKEYS });
    render(<LoginFlow />);
    expect(await card()).toHaveTextContent("Passkey: 2 passkey đã đăng ký");
    const list = screen.getByRole("list", { name: "Passkey đã đăng ký" });
    const [first, second] = within(list).getAllByRole("listitem");
    expect(first).toHaveTextContent("Laptop");
    expect(first).toHaveTextContent("Tạo ngày");
    expect(first).toHaveTextContent("Chưa dùng");
    expect(first).not.toHaveTextContent("đã đồng bộ");
    expect(second).toHaveTextContent("Điện thoại");
    expect(second).toHaveTextContent("Dùng lần cuối");
    expect(second).toHaveTextContent("đã đồng bộ");
  });

  it("falls back to the raw text for an unparsable date and to an empty list without passkeys", async () => {
    accountSetup({ passkeys: [{ ...PASSKEYS[0], created_at: "not-a-date" }] });
    render(<LoginFlow />);
    expect(await card()).toHaveTextContent("Tạo ngày not-a-date");
  });

  it("adds a passkey with the default name and no password field when there is no password", async () => {
    webauthn.create.mockResolvedValue(CREDENTIAL);
    const fetchMock = accountSetup({ has_password: false }, (url, init) => {
      if (url.endsWith("/me/passkeys/options")) return jsonResponse(CHALLENGE);
      if (url.endsWith("/me/passkeys") && init.method === "POST") return jsonResponse({ passkeys: PASSKEYS });
      return undefined;
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await card();
    expect(screen.queryByLabelText("Nhập lại mật khẩu để xác nhận", { selector: "#passkey-password" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Tên Passkey (không bắt buộc)")).toHaveValue("Passkey của tôi");
    await user.click(screen.getByRole("button", { name: "Thêm Passkey" }));
    expect(await screen.findByText("Đã thêm Passkey.")).toBeInTheDocument();
    expect(bodyOf(callsTo(fetchMock, "/me/passkeys/options")[0][1])).toEqual({});
    expect(bodyOf(callsTo(fetchMock, "/me/passkeys", "POST")[0][1])).toEqual({
      credential: CREDENTIAL,
      challenge_token: "tok",
      name: "Passkey của tôi",
    });
    expect(callsTo(fetchMock, "/auth/me").length).toBeGreaterThan(1); // Me refreshed
  });

  it("adds a passkey with a custom name and the re-entered password", async () => {
    webauthn.create.mockResolvedValue(CREDENTIAL);
    const fetchMock = accountSetup({}, (url, init) => {
      if (url.endsWith("/me/passkeys/options")) return jsonResponse(CHALLENGE);
      if (url.endsWith("/me/passkeys") && init.method === "POST") return jsonResponse({ passkeys: PASSKEYS });
      return undefined;
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await card();
    await user.click(screen.getByRole("button", { name: "Thêm Passkey" }));
    expect(await screen.findByText("Hãy nhập mật khẩu để xác nhận")).toBeInTheDocument();
    expect(callsTo(fetchMock, "/me/passkeys/options")).toHaveLength(0);
    await user.clear(screen.getByLabelText("Tên Passkey (không bắt buộc)"));
    await user.type(screen.getByLabelText("Tên Passkey (không bắt buộc)"), "Khóa USB");
    await user.type(screen.getByLabelText("Nhập lại mật khẩu để xác nhận"), "Pw-123456!");
    await user.click(screen.getByRole("button", { name: "Thêm Passkey" }));
    await screen.findByText("Đã thêm Passkey.");
    expect(bodyOf(callsTo(fetchMock, "/me/passkeys/options")[0][1])).toEqual({ password: "Pw-123456!" });
    expect(bodyOf(callsTo(fetchMock, "/me/passkeys", "POST")[0][1]).name).toBe("Khóa USB");
    expect(screen.getByLabelText("Nhập lại mật khẩu để xác nhận")).toHaveValue("");
  });

  it.each([
    ["a cancelled prompt", () => webauthn.create.mockRejectedValue(domError("NotAllowedError")), PASSKEY_CANCELLED],
    ["a device that already has this passkey", () => webauthn.create.mockRejectedValue(domError("InvalidStateError")), PASSKEY_DUPLICATE_DEVICE],
  ])("shows a friendly message for %s", async (_label, arrange, text) => {
    arrange();
    accountSetup({ has_password: false }, (url) => (url.endsWith("/me/passkeys/options") ? jsonResponse(CHALLENGE) : undefined));
    const user = userEvent.setup();
    render(<LoginFlow />);
    await card();
    await user.click(screen.getByRole("button", { name: "Thêm Passkey" }));
    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thêm Passkey" })).toBeEnabled();
  });

  it.each([
    [409, "This passkey is already registered"],
    [400, "Passkey registration failed"],
    [403, "Incorrect password"],
  ])("shows the server message for HTTP %s when adding", async (status, detail) => {
    webauthn.create.mockResolvedValue(CREDENTIAL);
    accountSetup({ has_password: false }, (url, init) => {
      if (url.endsWith("/me/passkeys/options")) return jsonResponse(CHALLENGE);
      if (url.endsWith("/me/passkeys") && init.method === "POST") return jsonResponse({ detail }, status);
      return undefined;
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await card();
    await user.click(screen.getByRole("button", { name: "Thêm Passkey" }));
    expect(await screen.findByText(detail)).toBeInTheDocument();
  });

  it("renames a passkey inline", async () => {
    const fetchMock = accountSetup({ passkeys: PASSKEYS }, (url, init) =>
      url.endsWith("/me/passkeys/7") && init.method === "PATCH" ? jsonResponse({ passkeys: PASSKEYS }) : undefined,
    );
    const user = userEvent.setup();
    render(<LoginFlow />);
    await card();
    const row = within(screen.getByRole("list", { name: "Passkey đã đăng ký" })).getAllByRole("listitem")[0];
    await user.click(within(row).getByRole("button", { name: "Đổi tên" }));
    await user.clear(within(row).getByLabelText("Tên mới"));
    await user.click(within(row).getByRole("button", { name: "Lưu tên" }));
    expect(await within(row).findByText("Hãy nhập tên cho Passkey")).toBeInTheDocument();
    await user.type(within(row).getByLabelText("Tên mới"), "Máy làm việc");
    await user.click(within(row).getByRole("button", { name: "Lưu tên" }));
    await waitFor(() => expect(callsTo(fetchMock, "/me/passkeys/7", "PATCH")).toHaveLength(1));
    expect(bodyOf(callsTo(fetchMock, "/me/passkeys/7", "PATCH")[0][1])).toEqual({ name: "Máy làm việc" });
    await waitFor(() => expect(screen.queryByLabelText("Tên mới")).not.toBeInTheDocument());
  });

  it("cancels a rename without calling the server", async () => {
    const fetchMock = accountSetup({ passkeys: PASSKEYS });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await card();
    await user.click(screen.getAllByRole("button", { name: "Đổi tên" })[0]);
    await user.type(screen.getByLabelText("Tên mới"), "x");
    await user.click(screen.getByRole("button", { name: "Hủy" }));
    expect(screen.queryByLabelText("Tên mới")).not.toBeInTheDocument();
    expect(callsTo(fetchMock, "/me/passkeys/7", "PATCH")).toHaveLength(0);
  });

  it("deletes a passkey after re-entering the password", async () => {
    const fetchMock = accountSetup({ passkeys: PASSKEYS }, (url, init) =>
      url.endsWith("/me/passkeys/8") && init.method === "DELETE" ? jsonResponse({ passkeys: [PASSKEYS[0]] }) : undefined,
    );
    const user = userEvent.setup();
    render(<LoginFlow />);
    await card();
    await user.click(screen.getAllByRole("button", { name: "Xóa" })[1]);
    await user.click(screen.getByRole("button", { name: "Xác nhận xóa" }));
    expect(await screen.findByText("Hãy nhập mật khẩu để xác nhận")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Nhập lại mật khẩu để xác nhận"), "Pw-123456!");
    await user.click(screen.getByRole("button", { name: "Xác nhận xóa" }));
    await waitFor(() => expect(callsTo(fetchMock, "/me/passkeys/8", "DELETE")).toHaveLength(1));
    expect(bodyOf(callsTo(fetchMock, "/me/passkeys/8", "DELETE")[0][1])).toEqual({ password: "Pw-123456!" });
  });

  it("deletes without a password field when the account has none, and can cancel", async () => {
    const fetchMock = accountSetup({ has_password: false, passkeys: PASSKEYS }, (url, init) =>
      url.endsWith("/me/passkeys/7") && init.method === "DELETE" ? jsonResponse({ passkeys: [PASSKEYS[1]] }) : undefined,
    );
    const user = userEvent.setup();
    render(<LoginFlow />);
    await card();
    await user.click(screen.getAllByRole("button", { name: "Xóa" })[0]);
    expect(screen.queryByLabelText("Nhập lại mật khẩu để xác nhận")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Hủy" }));
    expect(screen.queryByRole("button", { name: "Xác nhận xóa" })).not.toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Xóa" })[0]);
    await user.click(screen.getByRole("button", { name: "Xác nhận xóa" }));
    await waitFor(() => expect(callsTo(fetchMock, "/me/passkeys/7", "DELETE")).toHaveLength(1));
    expect(bodyOf(callsTo(fetchMock, "/me/passkeys/7", "DELETE")[0][1])).toEqual({});
  });

  it("shows the server message when deleting the last sign-in method (409)", async () => {
    accountSetup({ has_password: false, passkeys: [PASSKEYS[0]] }, (url, init) =>
      url.endsWith("/me/passkeys/7") && init.method === "DELETE"
        ? jsonResponse({ detail: "Keep at least one sign-in method" }, 409)
        : undefined,
    );
    const user = userEvent.setup();
    render(<LoginFlow />);
    await card();
    await user.click(screen.getByRole("button", { name: "Xóa" }));
    await user.click(screen.getByRole("button", { name: "Xác nhận xóa" }));
    expect(await screen.findByText("Keep at least one sign-in method")).toBeInTheDocument();
    expect(screen.getByText("Laptop")).toBeInTheDocument();
  });

  it("disables adding with a message when WebAuthn is unsupported", async () => {
    webauthn.supported = false;
    accountSetup();
    render(<LoginFlow />);
    await card();
    expect(screen.getByRole("button", { name: "Thêm Passkey" })).toBeDisabled();
    expect(screen.getByText(PASSKEY_UNSUPPORTED)).toBeInTheDocument();
  });

  it("tolerates a Me payload without passkeys", async () => {
    const { passkeys: _drop, ...legacy } = me;
    accountSetup(legacy as unknown as Partial<typeof me>);
    render(<LoginFlow />);
    expect(await card()).toHaveTextContent("Passkey: chưa có");
  });
});

describe("passkey helpers", () => {
  it("passkey ceremony wrappers pass options through and map errors", async () => {
    webauthn.start.mockResolvedValue("auth");
    webauthn.create.mockResolvedValue("reg");
    await expect(getPasskeyCredential({ a: 1 })).resolves.toBe("auth");
    await expect(createPasskeyCredential({ b: 2 })).resolves.toBe("reg");
    expect(webauthn.start).toHaveBeenCalledWith({ optionsJSON: { a: 1 } });
    expect(webauthn.create).toHaveBeenCalledWith({ optionsJSON: { b: 2 } });
    const boom = new Error("boom");
    webauthn.start.mockRejectedValue(boom);
    await expect(getPasskeyCredential({})).rejects.toBe(boom);
    webauthn.create.mockRejectedValue("not-an-error");
    await expect(createPasskeyCredential({})).rejects.toBe("not-an-error");
  });

  it("calls the documented endpoints with the documented bodies", async () => {
    const fetchMock = mockFetch((url) => jsonResponse(url.includes("passkey/options") || url.endsWith("/passkeys/options") ? CHALLENGE : { passkeys: [] }));
    await passkeyLoginOptions();
    await loginWithPasskey(CREDENTIAL, "t");
    await passkeyRegisterOptions("  ann ");
    await passkeyRegisterOptions("   ");
    await myPasskeyOptions("pw");
    await addPasskey(CREDENTIAL, "t", "  ");
    await renamePasskey(3, "n");
    await deletePasskey(3, "pw");
    const seen = fetchMock.mock.calls.map(([url, init]) => `${init?.method ?? "GET"} ${url.replace(/^.*\/auth/, "")}`);
    expect(seen).toEqual([
      "POST /passkey/options",
      "POST /passkey/login",
      "POST /register/passkey/options",
      "POST /register/passkey/options",
      "POST /me/passkeys/options",
      "POST /me/passkeys",
      "PATCH /me/passkeys/3",
      "DELETE /me/passkeys/3",
    ]);
    const bodies = fetchMock.mock.calls.map(([, init]) => init?.body);
    expect(JSON.parse(String(bodies[2]))).toEqual({ username: "ann" });
    expect(JSON.parse(String(bodies[3]))).toEqual({});
    expect(JSON.parse(String(bodies[5]))).toEqual({ credential: CREDENTIAL, challenge_token: "t" });
  });

  it("registerCombined only adds the passkey fields when both parts are present", async () => {
    const fetchMock = mockFetch(() => jsonResponse(session, 201));
    await registerCombined({ username: "a", passkeyCredential: CREDENTIAL });
    expect([...(fetchMock.mock.calls[0][1].body as FormData).keys()]).toEqual(["username"]);
    await registerCombined({ passkeyCredential: CREDENTIAL, passkeyChallengeToken: "t" });
    expect([...(fetchMock.mock.calls[1][1].body as FormData).keys()]).toEqual(["passkey_credential", "passkey_challenge_token"]);
  });
});

describe("Passkey limit on /account", () => {
  beforeEach(() => {
    window.location.hash = "#cach-passkey"; // the account page opens on this tab
  });

  const many = (count: number): PasskeyItem[] =>
    Array.from({ length: count }, (_, index) => ({ ...PASSKEYS[0], id: 100 + index, name: `Khóa ${index}` }));

  it("disables the add form and explains the cap at 10 passkeys", async () => {
    accountSetup({ passkeys: many(10) });
    render(<LoginFlow />);
    await card();
    expect(screen.getByText("Tối đa 10 Passkey cho mỗi tài khoản")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thêm Passkey" })).toBeDisabled();
    expect(screen.getByLabelText("Tên Passkey (không bắt buộc)")).toBeDisabled();
  });

  it("keeps the form usable at 9 passkeys", async () => {
    accountSetup({ passkeys: many(9) });
    render(<LoginFlow />);
    await card();
    expect(screen.queryByText("Tối đa 10 Passkey cho mỗi tài khoản")).not.toBeInTheDocument();
    // enabled once WebAuthn support has been detected (an effect), so wait for it
    await waitFor(() => expect(screen.getByRole("button", { name: "Thêm Passkey" })).toBeEnabled());
  });

  it("shows the Vietnamese text when the server answers 409 Passkey limit reached", async () => {
    accountSetup({ passkeys: many(2) }, (url) =>
      url.endsWith("/me/passkeys/options") ? jsonResponse({ detail: "Passkey limit reached" }, 409) : undefined,
    );
    const user = userEvent.setup();
    render(<LoginFlow />);
    await card();
    await user.type(screen.getByLabelText("Nhập lại mật khẩu để xác nhận"), "Pw-123456!");
    await user.click(screen.getByRole("button", { name: "Thêm Passkey" }));
    expect((await screen.findAllByText("Tối đa 10 Passkey cho mỗi tài khoản")).length).toBeGreaterThan(0);
  });
});
