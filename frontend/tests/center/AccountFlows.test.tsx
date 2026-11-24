import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginFlow from "../../app/center/components/LoginFlow";
import { headerOf, jsonResponse, me, mockFetch, session } from "./helpers";
import { tabNames } from "./tabs";

const goTo = vi.hoisted(() => vi.fn());
vi.mock("../../app/center/lib/navigate", async (original) => ({
  ...(await original<typeof import("../../app/center/lib/navigate")>()),
  goTo,
}));

const webauthn = vi.hoisted(() => ({ supported: true, create: vi.fn() }));
vi.mock("@simplewebauthn/browser", () => ({
  browserSupportsWebAuthn: () => webauthn.supported,
  startAuthentication: vi.fn(),
  startRegistration: webauthn.create,
}));

// The real recorders need hardware; these stand-ins "record" instantly.
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

const CONFIG = { google_client_id: null, biometrics_enabled: true };
const SECOND_FACTOR = "Yêu cầu giọng nói/khuôn mặt sau khi đăng nhập bằng mật khẩu hoặc Google";

type Account = typeof me;

// The account page shows one tab at a time: a test opens the tab of the feature it exercises, as the URL hash would.
const openTab = (tab: string) => {
  window.location.hash = `#cach-${tab}`;
};
const GOOGLE = { google_client_id: "cid", biometrics_enabled: false };

function setupAccount(account: Partial<Account> = {}, config: unknown = CONFIG, extra?: (url: string, init: RequestInit) => Response | undefined) {
  const current = { ...me, ...account };
  return mockFetch((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/sessions")) return jsonResponse([]);
    if (url.endsWith("/auth/config")) return jsonResponse(config);
    if (url.endsWith("/auth/me") && (init.method ?? "GET") === "GET") return jsonResponse(current);
    if (url.endsWith("/auth/me") && init.method === "DELETE") return jsonResponse(null, 204);
    if (url.endsWith("/auth/logout")) return jsonResponse(null, 204);
    if (url.endsWith("/me/password")) return jsonResponse({ ...session, csrf_token: "csrf-new" });
    return jsonResponse({});
  });
}

beforeEach(() => {
  window.location.hash = "";
  goTo.mockReset();
  webauthn.supported = true;
  webauthn.create.mockReset();
});

describe("AccountView", () => {
  it("opens the sign-in mode, and does not offer Cập nhật, when signed out", async () => {
    mockFetch((url) => (url.endsWith("/auth/config") ? jsonResponse(CONFIG) : jsonResponse({ detail: "x" }, 401)));
    render(<LoginFlow />);
    expect(await screen.findByLabelText(/^Tên đăng nhập/)).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Cập nhật" })).not.toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });

  it("sends the visitor to sign in when the session ends while the account is loading", async () => {
    let meCalls = 0;
    mockFetch((url) => {
      if (url.endsWith("/auth/config")) return jsonResponse(CONFIG);
      if (url.endsWith("/auth/refresh")) return jsonResponse({ detail: "x" }, 401);
      if (url.endsWith("/auth/me")) return (meCalls += 1) === 1 ? jsonResponse(me) : jsonResponse({ detail: "x" }, 401);
      return jsonResponse([]);
    });
    render(<LoginFlow />);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/user"));
  });

  it("shows an error with retry when loading the account fails", async () => {
    let meCalls = 0;
    mockFetch((url) => {
      if (url.endsWith("/auth/config")) return jsonResponse(CONFIG);
      if (url.endsWith("/auth/me")) {
        meCalls += 1; // 1: the page's session check, 2: the account load that fails, then it works again
        return meCalls === 2 ? jsonResponse({ detail: "down" }, 503) : jsonResponse(me);
      }
      return jsonResponse([]);
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    expect(await screen.findByRole("alert")).toHaveTextContent("down");
    await user.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByRole("form", { name: "Đổi mật khẩu" })).toBeInTheDocument();
  });

  it("renders profile text and hides biometrics when disabled", async () => {
    setupAccount({ username: "<b>bob</b>", email: "b@example.com" }, { google_client_id: null, biometrics_enabled: false });
    render(<LoginFlow />);
    expect(await screen.findByText("<b>bob</b>")).toBeInTheDocument(); // shown as text, in the username block
    expect(screen.getByText(/b@example.com/)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Đăng nhập bằng giọng nói" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Bảo mật nâng cao" })).not.toBeInTheDocument();
  });

  it("changes the password, validates input, and stores the new csrf token", async () => {
    const fetchMock = setupAccount();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await screen.findByRole("form", { name: "Đổi mật khẩu" });
    await user.type(screen.getByLabelText("Mật khẩu hiện tại"), "Oldpassword-1");
    await user.type(screen.getByLabelText("Mật khẩu mới"), "short");
    await user.type(screen.getByLabelText("Nhập lại mật khẩu mới"), "short");
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Mật khẩu cần 8-128 ký tự");

    await user.clear(screen.getByLabelText("Mật khẩu mới"));
    await user.type(screen.getByLabelText("Mật khẩu mới"), "short12345"); // long enough but missing classes
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("gồm chữ thường, chữ hoa, số và ký tự đặc biệt");

    await user.clear(screen.getByLabelText("Mật khẩu mới"));
    await user.type(screen.getByLabelText("Mật khẩu mới"), "Short-12345");
    await user.clear(screen.getByLabelText("Nhập lại mật khẩu mới"));
    await user.type(screen.getByLabelText("Nhập lại mật khẩu mới"), "999");
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    expect(await screen.findByText("Mật khẩu nhập lại không khớp")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Nhập lại mật khẩu mới"));
    await user.type(screen.getByLabelText("Nhập lại mật khẩu mới"), "Short-12345");
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    expect(await screen.findByText("Đã cập nhật mật khẩu.")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url]) => url.endsWith("/me/password"));
    expect(JSON.parse(call?.[1].body as string)).toEqual({ new_password: "Short-12345", current_password: "Oldpassword-1" });
  });

  it("signs out everywhere from the sessions section and goes to the sign-in page", async () => {
    setupAccount();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await user.click(await screen.findByRole("button", { name: "Đăng xuất mọi nơi" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/user"));
  });

  it("asks for no current password on a Google-only account and surfaces 429", async () => {
    setupAccount({ has_password: false }, CONFIG, (url) =>
      url.endsWith("/me/password") ? jsonResponse({ detail: "x" }, 429) : undefined,
    );
    const user = userEvent.setup();
    render(<LoginFlow />);
    await screen.findByRole("form", { name: "Đổi mật khẩu" });
    expect(screen.queryByLabelText("Mật khẩu hiện tại")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Mật khẩu mới"), "Longenough-1");
    await user.type(screen.getByLabelText("Nhập lại mật khẩu mới"), "Longenough-1");
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    expect(await screen.findByText("Thử quá nhiều lần, hãy thử lại sau")).toBeInTheDocument();
  });

  it("requires typed confirmation and a password before deleting the account", async () => {
    const fetchMock = setupAccount();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await screen.findByRole("form", { name: "Xóa tài khoản" });
    const button = screen.getByRole("button", { name: "Xóa tài khoản của tôi" });
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText("Xác nhận"), "xoa");
    expect(button).toBeDisabled();
    await user.clear(screen.getByLabelText("Xác nhận"));
    await user.type(screen.getByLabelText("Xác nhận"), "XOA");
    expect(button).toBeEnabled();
    const deleteForm = screen.getByRole("form", { name: "Xóa tài khoản" });
    await user.type(screen.getByLabelText("Nhập lại mật khẩu để xác nhận"), "Secret-Pass1");
    await user.click(button);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const call = fetchMock.mock.calls.find(([, init]) => init.method === "DELETE");
    expect(call?.[1].body).toBe(JSON.stringify({ password: "Secret-Pass1" }));
    expect(headerOf(call?.[1], "Content-Type")).toBe("application/json");
  });

  it("shows a delete error without leaving the page", async () => {
    setupAccount({}, CONFIG, (url, init) => (init.method === "DELETE" ? jsonResponse({ detail: "Wrong password" }, 403) : undefined));
    const user = userEvent.setup();
    render(<LoginFlow />);
    const form = await screen.findByRole("form", { name: "Xóa tài khoản" });
    await user.type(screen.getByLabelText("Xác nhận"), "XOA");
    await user.type(screen.getByLabelText("Nhập lại mật khẩu để xác nhận"), "x");
    await user.click(screen.getByRole("button", { name: "Xóa tài khoản của tôi" }));
    expect(await screen.findByText("Wrong password")).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });

  it("links a Google account when configured and not yet linked", async () => {
    openTab("google");
    setupAccount({}, GOOGLE);
    vi.spyOn(document.head, "appendChild").mockImplementation((node) => {
      queueMicrotask(() => (node as HTMLScriptElement).onerror?.(new Event("error")));
      return node;
    });
    render(<LoginFlow />);
    expect(await screen.findByRole("region", { name: "Liên kết tài khoản Google" })).toBeInTheDocument();
    vi.restoreAllMocks();
  });

  it("tells voice and webcam accounts that no username is needed", async () => {
    setupAccount({ voice_login: true, webcam_login: true });
    render(<LoginFlow />);
    expect(await screen.findAllByText("Đăng nhập không cần tên đăng nhập")).toHaveLength(2);
  });

  it("shows the no-username line only for the enabled biometric row", async () => {
    setupAccount({ voice_login: true, webcam_login: false });
    render(<LoginFlow />);
    expect(await screen.findAllByText("Đăng nhập không cần tên đăng nhập")).toHaveLength(1);
  });

  it("hides the no-username line when voice and webcam are off", async () => {
    setupAccount({ voice_login: false, webcam_login: false });
    render(<LoginFlow />);
    await screen.findByRole("form", { name: "Đổi mật khẩu" });
    expect(screen.queryByText(/không cần tên đăng nhập/)).not.toBeInTheDocument();
  });

  it("shows each method's state in its own tab", async () => {
    setupAccount({ has_password: true, google_linked: true, email: "b@example.com", voice_login: true, webcam_login: false }, { google_client_id: "cid", biometrics_enabled: true });
    render(<LoginFlow />);
    expect(await screen.findByRole("region", { name: "Mật khẩu" })).toHaveTextContent("Mật khẩu: đã đặt");
    // Every panel stays mounted but only the open tab's is shown: read the others with `hidden`.
    const card = (name: string) => screen.getByRole("region", { name, hidden: true });
    expect(card("Google")).toHaveTextContent("Google: đã liên kết với b@example.com");
    expect(card("Giọng nói")).toHaveTextContent("Giọng nói: đã bật");
    expect(card("Webcam (khuôn mặt)")).toHaveTextContent("Webcam (khuôn mặt): chưa bật");
    const button = (name: string) => screen.getByRole("button", { name, hidden: true });
    expect(button("Hủy giọng nói")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hủy webcam", hidden: true })).not.toBeInTheDocument();
    // the apply buttons are the page's one "Đổi tài khoản"; each form is still there
    expect(screen.getByRole("form", { name: "Đăng nhập bằng giọng nói", hidden: true })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Đăng nhập bằng webcam (khuôn mặt)", hidden: true })).toBeInTheDocument();
    // voice + webcam liveness warnings and the 2FA warning. "At least": the passkey row adds one more
    // note once it has detected (after mount) that this test browser lacks WebAuthn, so an exact count
    // depended on when the assertion ran.
    expect(screen.getAllByRole("note", { hidden: true }).length).toBeGreaterThanOrEqual(3);
  });

  it("offers to set a password when there is none", async () => {
    setupAccount({ has_password: false });
    render(<LoginFlow />);
    const card = await screen.findByRole("region", { name: "Mật khẩu" });
    expect(card).toHaveTextContent("Mật khẩu: chưa đặt");
    expect(screen.getByRole("form", { name: "Đổi mật khẩu" })).toHaveTextContent("Đặt mật khẩu");
  });

  it("adds voice with password re-auth", async () => {
    openTab("voice");
    const fetchMock = setupAccount();
    const user = userEvent.setup();
    render(<LoginFlow />);
    const form = await screen.findByRole("form", { name: "Đăng nhập bằng giọng nói" });
    // Nothing recorded: the page's button has nothing to apply, and the form itself (Enter) says why.
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Chưa có thay đổi nào/); // the summary line says the same, but only this is an alert
    fireEvent.submit(form);
    expect(await screen.findByText("Hãy ghi giọng nói trước khi lưu")).toBeInTheDocument();
    await user.click(within(form).getByRole("button", { name: "fake voice" }));
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    expect(await screen.findByText("Hãy nhập mật khẩu để xác nhận")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Nhập lại mật khẩu để xác nhận"), "Pw-Pass-1");
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    expect(await screen.findByText("Đã lưu giọng nói.")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url, init]) => url.endsWith("/me/voice") && init.method === "POST");
    const body = call?.[1].body as FormData;
    expect(body.get("password")).toBe("Pw-Pass-1");
    expect(body.get("audio")).toBeInstanceOf(Blob);
  });

  it("adds a webcam clip without a password when the account has none", async () => {
    openTab("webcam");
    const fetchMock = setupAccount({ has_password: false, google_linked: true });
    const user = userEvent.setup();
    render(<LoginFlow />);
    const form = await screen.findByRole("form", { name: "Đăng nhập bằng webcam (khuôn mặt)" });
    expect(screen.queryByLabelText("Nhập lại mật khẩu để xác nhận")).toBeNull();
    await user.click(within(form).getByRole("button", { name: "fake webcam" }));
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    expect(await screen.findByText("Đã lưu webcam.")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url, init]) => url.endsWith("/me/webcam") && init.method === "POST");
    const body = call?.[1].body as FormData;
    expect(body.has("password")).toBe(false);
    expect(body.get("video")).toBeInstanceOf(Blob);
    expect(body.has("audio")).toBe(false);
  });

  it("replaces an enabled webcam method", async () => {
    openTab("webcam");
    const fetchMock = setupAccount({ webcam_login: true, has_face: true, has_audio: true });
    const user = userEvent.setup();
    render(<LoginFlow />);
    const form = await screen.findByRole("form", { name: "Đăng nhập bằng webcam (khuôn mặt)" });
    await user.click(within(form).getByRole("button", { name: "fake webcam" }));
    await user.type(screen.getByLabelText("Nhập lại mật khẩu để xác nhận"), "Pw-Pass-1");
    await user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url, init]) => url.endsWith("/me/webcam") && init.method === "POST")).toBe(true),
    );
  });

  it("removes voice only after the password is entered", async () => {
    openTab("voice");
    const fetchMock = setupAccount({ voice_login: true, webcam_login: true, has_password: true });
    const user = userEvent.setup();
    render(<LoginFlow />);
    const voice = await screen.findByRole("form", { name: "Đăng nhập bằng giọng nói" });
    await user.click(within(voice).getByRole("button", { name: "Hủy giọng nói" }));
    expect(await screen.findByText("Hãy nhập mật khẩu để xác nhận")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Nhập lại mật khẩu để xác nhận"), "Pw-Pass-1");
    await user.click(within(voice).getByRole("button", { name: "Hủy giọng nói" }));
    await waitFor(() => {
      const del = fetchMock.mock.calls.find(([url, init]) => url.endsWith("/me/voice") && init.method === "DELETE");
      expect((del?.[1].body as FormData).get("password")).toBe("Pw-Pass-1");
    });
  });

  it("removes webcam without a password on a Google-only account", async () => {
    openTab("webcam");
    const fetchMock = setupAccount({ webcam_login: true, has_password: false, google_linked: true });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await user.click(await screen.findByRole("button", { name: "Hủy webcam" }));
    await waitFor(() => {
      const del = fetchMock.mock.calls.find(([url, init]) => url.endsWith("/me/webcam") && init.method === "DELETE");
      expect((del?.[1].body as FormData).has("password")).toBe(false);
    });
  });

  it("shows the server message when removing the last sign-in method", async () => {
    openTab("voice");
    setupAccount({ voice_login: true, has_password: false }, CONFIG, (url, init) =>
      url.endsWith("/me/voice") && init.method === "DELETE"
        ? jsonResponse({ detail: "Keep at least one sign-in method" }, 409)
        : undefined,
    );
    const user = userEvent.setup();
    render(<LoginFlow />);
    await user.click(await screen.findByRole("button", { name: "Hủy giọng nói" }));
    expect(await screen.findByText("Keep at least one sign-in method")).toBeInTheDocument();
  });

  it("hides voice and webcam methods when biometrics are not configured", async () => {
    setupAccount({}, { google_client_id: null, biometrics_enabled: false });
    render(<LoginFlow />);
    const nav = await screen.findByRole("navigation", { name: "Cài đặt tài khoản" });
    expect(within(nav).queryByRole("link", { name: "Giọng nói" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Webcam (khuôn mặt)" })).not.toBeInTheDocument();
  });

  it("keeps the second-factor switch off and blocked until a sample is saved", async () => {
    openTab("webcam");
    setupAccount({ has_audio: false, has_face: false });
    render(<LoginFlow />);
    const form = await screen.findByRole("form", { name: SECOND_FACTOR });
    expect(form).toHaveTextContent(/đang TẮT/);
    expect(form).toHaveTextContent(/Cần lưu ít nhất một mẫu/);
    expect(screen.getByRole("button", { name: "Bật yêu cầu xác minh sinh trắc học" })).toBeDisabled();
  });

  it("turns the second factor on after re-entering the password", async () => {
    openTab("webcam");
    const fetchMock = setupAccount({ has_audio: true, has_face: false });
    const user = userEvent.setup();
    render(<LoginFlow />);
    const form = await screen.findByRole("form", { name: SECOND_FACTOR });
    expect(screen.getByRole("heading", { name: "Bảo mật nâng cao (tùy chọn)" })).toBeInTheDocument();
    expect(form).toHaveTextContent(/webcam/);
    await user.type(screen.getByLabelText("Nhập lại mật khẩu để xác nhận"), "Pw-Pass-1");
    await user.click(screen.getByRole("button", { name: "Bật yêu cầu xác minh sinh trắc học" }));
    await waitFor(() => {
      const put = fetchMock.mock.calls.find(([url, init]) => url.endsWith("/me/biometric-2fa") && init.method === "PUT");
      expect((put?.[1].body as FormData).get("enabled")).toBe("true");
      expect((put?.[1].body as FormData).get("password")).toBe("Pw-Pass-1");
    });
  });

  it("shows the second factor as on and offers to turn it off", async () => {
    openTab("webcam");
    setupAccount({ has_audio: true, require_biometric_2fa: true });
    render(<LoginFlow />);
    const form = await screen.findByRole("form", { name: SECOND_FACTOR });
    expect(form).toHaveTextContent(/đang BẬT/);
    expect(screen.getByRole("button", { name: "Tắt yêu cầu xác minh sinh trắc học" })).toBeEnabled();
  });

  it("will not unlink Google while the account has no password", async () => {
    openTab("google");
    setupAccount({ google_linked: true, has_password: false, email: "g@example.com" }, GOOGLE);
    render(<LoginFlow />);
    expect(await screen.findByText("Hãy đặt mật khẩu trước khi hủy liên kết Google.")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Hủy liên kết Google" })).not.toBeInTheDocument();
  });

  it("unlinks Google after re-entering the password", async () => {
    openTab("google");
    const fetchMock = setupAccount({ google_linked: true, has_password: true, email: "g@example.com" }, GOOGLE);
    const user = userEvent.setup();
    render(<LoginFlow />);
    const form = await screen.findByRole("form", { name: "Hủy liên kết Google" });
    await user.type(screen.getByLabelText("Nhập lại mật khẩu để xác nhận"), "Pw-Pass-1");
    await user.click(screen.getByRole("button", { name: "Hủy liên kết Google" }));
    await waitFor(() => {
      const del = fetchMock.mock.calls.find(([url, init]) => url.endsWith("/auth/me/google") && init.method === "DELETE");
      expect(JSON.parse(del?.[1].body as string)).toEqual({ password: "Pw-Pass-1" });
    });
  });
});

describe("AccountView password confirmation", () => {
  it("has one re-enter-password field, at the end of the username block, between sessions and delete", async () => {
    setupAccount();
    render(<LoginFlow />);
    await screen.findByRole("form", { name: "Đổi mật khẩu" });
    expect(screen.getAllByLabelText("Nhập lại mật khẩu để xác nhận")).toHaveLength(1);
    const field = screen.getByLabelText("Nhập lại mật khẩu để xác nhận");
    const username = screen.getByRole("form", { name: "Đổi tên đăng nhập" });
    const sessions = screen.getByRole("region", { name: "Thiết bị và phiên đăng nhập" });
    const remove = screen.getByRole("form", { name: "Xóa tài khoản" });
    const follows = (a: Element, b: Element) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
    expect(follows(sessions, username)).toBe(true);
    expect(follows(username, field)).toBe(true); // after the form, inside the same card
    expect(username.closest("section")).toContainElement(field);
    expect(username).not.toContainElement(field); // so Enter in it does not submit only the username
    expect(follows(field, remove)).toBe(true);
  });

  it("has no such field for an account without a password", async () => {
    setupAccount({ has_password: false, google_linked: true });
    render(<LoginFlow />);
    await screen.findByRole("form", { name: "Đổi mật khẩu" });
    expect(screen.queryByLabelText("Nhập lại mật khẩu để xác nhận")).toBeNull();
  });
});

describe("AccountView tabs", () => {
  const ALL_ON = { google_client_id: "cid", biometrics_enabled: true, email_enabled: true, phone_enabled: true };
  const BAR = "Cài đặt tài khoản";
  // The bar is built before the config arrives: wait until it lists what the config should add.
  const waitForLabels = (user: ReturnType<typeof userEvent.setup>, expected: string[]) =>
    waitFor(async () => expect(await tabNames(user, BAR)).toEqual(expected));

  it("has one tab per method, in the same groups as the sign-in page", async () => {
    setupAccount({}, ALL_ON);
    const user = userEvent.setup();
    render(<LoginFlow />);
    await waitForLabels(user, [
      "Mật khẩu", "Webcam (khuôn mặt)", "Giọng nói", "Mã TOTP", "Mã khôi phục", "Email", "SMS", "Google", "Passkey", "Mã QR",
    ]);
  });

  it("starts on the password tab and shows only its panel", async () => {
    setupAccount({}, ALL_ON);
    render(<LoginFlow />);
    expect(await screen.findByRole("form", { name: "Đổi mật khẩu" })).toBeVisible();
    expect(screen.queryByRole("region", { name: "Email" })).not.toBeInTheDocument();
  });

  it("drops the Email and SMS tabs when the server has neither channel", async () => {
    const fetchMock = setupAccount({}, { google_client_id: null, biometrics_enabled: false });
    const user = userEvent.setup();
    render(<LoginFlow />);
    await screen.findByRole("navigation", { name: BAR });
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url.endsWith("/auth/config"))).toBe(true));
    await waitForLabels(user, ["Mật khẩu", "Mã TOTP", "Mã khôi phục", "Passkey", "Mã QR"]);
  });

  it("opens the tab holding the TOTP card from its own hash", async () => {
    openTab("totp");
    setupAccount();
    render(<LoginFlow />);
    expect(await screen.findByRole("region", { name: "Xác thực hai bước (TOTP)" })).toBeVisible();
  });

  it("opens the Google tab for the old #lien-ket-google anchor", async () => {
    window.location.hash = "#lien-ket-google";
    setupAccount({}, GOOGLE);
    render(<LoginFlow />);
    expect(await screen.findByRole("region", { name: "Google" })).toBeVisible();
  });

  it("explains QR sign-in in the last tab", async () => {
    openTab("qr");
    setupAccount();
    render(<LoginFlow />);
    const qr = await screen.findByRole("region", { name: "Đăng nhập bằng mã QR" });
    expect(within(qr).getByRole("link", { name: "Mở trang đăng nhập" })).toHaveAttribute("href", "/user");
  });

  it("a signed-in person sees only the Cập nhật mode, opened on it", async () => {
    setupAccount();
    render(<LoginFlow />);
    const modes = await screen.findByRole("tablist", { name: "Chế độ" });
    expect(within(modes).getAllByRole("tab").map((mode) => mode.textContent)).toEqual(["Cập nhật"]);
    expect(within(modes).getByRole("tab", { name: "Cập nhật" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("form", { name: "Đổi mật khẩu" })).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });

  it("has no sign-in or sign-up tab once signed in", async () => {
    setupAccount();
    render(<LoginFlow />);
    await screen.findByRole("form", { name: "Đổi mật khẩu" });
    expect(screen.queryByRole("tab", { name: "Đăng nhập" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Đăng ký" })).not.toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });
});
