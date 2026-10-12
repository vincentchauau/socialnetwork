import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AccountView from "../app/components/AccountView";
import { headerOf, jsonResponse, me, mockFetch, session } from "./helpers";

const goTo = vi.hoisted(() => vi.fn());
vi.mock("../app/lib/navigate", async (original) => ({
  ...(await original<typeof import("../app/lib/navigate")>()),
  goTo,
}));

// The real recorders need hardware; these stand-ins "record" instantly.
vi.mock("../app/components/AudioRecord", () => ({
  default: ({ onRecorded }: { onRecorded: (b: Blob) => void }) => (
    <button type="button" onClick={() => onRecorded(new Blob(["a"]))}>fake voice</button>
  ),
}));
vi.mock("../app/components/VideoRecord", () => ({
  default: ({ onRecorded }: { onRecorded: (b: Blob) => void }) => (
    <button type="button" onClick={() => onRecorded(new Blob(["v"]))}>fake webcam</button>
  ),
}));

const CONFIG = { google_client_id: null, biometrics_enabled: true };
const SECOND_FACTOR = "Yêu cầu giọng nói/khuôn mặt sau khi đăng nhập bằng mật khẩu hoặc Google";

type Account = typeof me;

function setupAccount(account: Partial<Account> = {}, config: unknown = CONFIG, extra?: (url: string, init: RequestInit) => Response | undefined) {
  const current = { ...me, ...account };
  return mockFetch((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/config")) return jsonResponse(config);
    if (url.endsWith("/auth/me") && (init.method ?? "GET") === "GET") return jsonResponse(current);
    if (url.endsWith("/auth/me") && init.method === "DELETE") return jsonResponse(null, 204);
    if (url.endsWith("/auth/logout")) return jsonResponse(null, 204);
    if (url.endsWith("/me/password")) return jsonResponse({ ...session, csrf_token: "csrf-new" });
    return jsonResponse({});
  });
}

beforeEach(() => goTo.mockReset());

describe("AccountView", () => {
  it("redirects to login when signed out", async () => {
    mockFetch((url) => (url.endsWith("/auth/config") ? jsonResponse(CONFIG) : jsonResponse({ detail: "x" }, 401)));
    render(<AccountView />);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/login?next=/account"));
  });

  it("shows an error with retry when loading fails", async () => {
    let fail = true;
    mockFetch((url) => {
      if (url.endsWith("/auth/config")) return jsonResponse(CONFIG);
      return fail ? jsonResponse({ detail: "down" }, 503) : jsonResponse(me);
    });
    const user = userEvent.setup();
    render(<AccountView />);
    expect(await screen.findByRole("alert")).toHaveTextContent("down");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByRole("heading", { name: "Xin chào, ann" })).toBeInTheDocument();
  });

  it("renders profile text and hides biometrics when disabled", async () => {
    setupAccount({ username: "<b>bob</b>", email: "b@example.com" }, { google_client_id: null, biometrics_enabled: false });
    render(<AccountView />);
    expect(await screen.findByRole("heading", { name: "Xin chào, <b>bob</b>" })).toBeInTheDocument();
    expect(screen.getByText(/b@example.com/)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Đăng nhập bằng giọng nói" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Bảo mật nâng cao" })).not.toBeInTheDocument();
  });

  it("changes the password, validates input, and stores the new csrf token", async () => {
    const fetchMock = setupAccount();
    const user = userEvent.setup();
    render(<AccountView />);
    await screen.findByRole("form", { name: "Đổi mật khẩu" });
    await user.type(screen.getByLabelText("Mật khẩu hiện tại"), "oldpassword");
    await user.type(screen.getByLabelText("Mật khẩu mới"), "short");
    await user.type(screen.getByLabelText("Nhập lại mật khẩu mới"), "short");
    await user.click(screen.getByRole("button", { name: "Cập nhật mật khẩu" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Mật khẩu cần ít nhất 8 ký tự");

    await user.type(screen.getByLabelText("Mật khẩu mới"), "12345");
    await user.type(screen.getByLabelText("Nhập lại mật khẩu mới"), "999");
    await user.click(screen.getByRole("button", { name: "Cập nhật mật khẩu" }));
    expect(await screen.findByText("Mật khẩu nhập lại không khớp")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Nhập lại mật khẩu mới"));
    await user.type(screen.getByLabelText("Nhập lại mật khẩu mới"), "short12345");
    await user.click(screen.getByRole("button", { name: "Cập nhật mật khẩu" }));
    expect(await screen.findByText("Đã cập nhật mật khẩu.")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url]) => url.endsWith("/me/password"));
    expect(JSON.parse(call?.[1].body as string)).toEqual({ new_password: "short12345", current_password: "oldpassword" });

    await user.click(screen.getByRole("button", { name: "Đăng xuất mọi nơi" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/login"));
  });

  it("asks for no current password on a Google-only account and surfaces 429", async () => {
    setupAccount({ has_password: false }, CONFIG, (url) =>
      url.endsWith("/me/password") ? jsonResponse({ detail: "x" }, 429) : undefined,
    );
    const user = userEvent.setup();
    render(<AccountView />);
    await screen.findByRole("form", { name: "Đổi mật khẩu" });
    expect(screen.queryByLabelText("Mật khẩu hiện tại")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Mật khẩu mới"), "longenough1");
    await user.type(screen.getByLabelText("Nhập lại mật khẩu mới"), "longenough1");
    await user.click(screen.getByRole("button", { name: "Cập nhật mật khẩu" }));
    expect(await screen.findByText("Thử quá nhiều lần, hãy thử lại sau")).toBeInTheDocument();
  });

  it("requires typed confirmation and a password before deleting the account", async () => {
    const fetchMock = setupAccount();
    const user = userEvent.setup();
    render(<AccountView />);
    await screen.findByRole("form", { name: "Xóa tài khoản" });
    const button = screen.getByRole("button", { name: "Xóa tài khoản của tôi" });
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText("Xác nhận"), "xoa");
    expect(button).toBeDisabled();
    await user.clear(screen.getByLabelText("Xác nhận"));
    await user.type(screen.getByLabelText("Xác nhận"), "XOA");
    expect(button).toBeEnabled();
    const deleteForm = screen.getByRole("form", { name: "Xóa tài khoản" });
    await user.type(deleteForm.querySelector('input[type="password"]') as HTMLInputElement, "secret-pass");
    await user.click(button);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const call = fetchMock.mock.calls.find(([, init]) => init.method === "DELETE");
    expect(call?.[1].body).toBe(JSON.stringify({ password: "secret-pass" }));
    expect(headerOf(call?.[1], "Content-Type")).toBe("application/json");
  });

  it("shows a delete error without leaving the page", async () => {
    setupAccount({}, CONFIG, (url, init) => (init.method === "DELETE" ? jsonResponse({ detail: "Wrong password" }, 403) : undefined));
    const user = userEvent.setup();
    render(<AccountView />);
    const form = await screen.findByRole("form", { name: "Xóa tài khoản" });
    await user.type(screen.getByLabelText("Xác nhận"), "XOA");
    await user.type(form.querySelector('input[type="password"]') as HTMLInputElement, "x");
    await user.click(screen.getByRole("button", { name: "Xóa tài khoản của tôi" }));
    expect(await screen.findByText("Wrong password")).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });

  it("links a Google account when configured and not yet linked", async () => {
    setupAccount({}, { google_client_id: "cid", biometrics_enabled: false });
    vi.spyOn(document.head, "appendChild").mockImplementation((node) => {
      queueMicrotask(() => (node as HTMLScriptElement).onerror?.(new Event("error")));
      return node;
    });
    render(<AccountView />);
    expect(await screen.findByRole("region", { name: "Liên kết tài khoản Google" })).toBeInTheDocument();
    vi.restoreAllMocks();
  });

  it("tells voice and webcam accounts that no username is needed", async () => {
    setupAccount({ voice_login: true, webcam_login: true });
    render(<AccountView />);
    expect(await screen.findAllByText("Đăng nhập không cần tên đăng nhập")).toHaveLength(2);
  });

  it("shows the no-username line only for the enabled biometric row", async () => {
    setupAccount({ voice_login: true, webcam_login: false });
    render(<AccountView />);
    expect(await screen.findAllByText("Đăng nhập không cần tên đăng nhập")).toHaveLength(1);
  });

  it("hides the no-username line when voice and webcam are off", async () => {
    setupAccount({ voice_login: false, webcam_login: false });
    render(<AccountView />);
    await screen.findByRole("heading", { name: /Xin chào/ });
    expect(screen.queryByText(/không cần tên đăng nhập/)).not.toBeInTheDocument();
  });

  it("lists the four sign-in methods with their state", async () => {
    setupAccount({ has_password: true, google_linked: true, email: "b@example.com", voice_login: true, webcam_login: false });
    render(<AccountView />);
    const card = await screen.findByRole("region", { name: "Các cách đăng nhập" });
    expect(card).toHaveTextContent("Mật khẩu: đã đặt");
    expect(card).toHaveTextContent("Google: đã liên kết với b@example.com");
    expect(card).toHaveTextContent("Giọng nói: đã bật");
    expect(card).toHaveTextContent("Webcam (khuôn mặt): chưa bật");
    expect(screen.getByRole("button", { name: "Hủy giọng nói" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hủy webcam" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thay giọng nói" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Lưu webcam" })).toBeInTheDocument();
    expect(screen.getAllByRole("note")).toHaveLength(3); // voice + webcam liveness warnings and the 2FA warning
  });

  it("offers to set a password when there is none", async () => {
    setupAccount({ has_password: false });
    render(<AccountView />);
    const card = await screen.findByRole("region", { name: "Các cách đăng nhập" });
    expect(card).toHaveTextContent("Mật khẩu: chưa đặt");
    expect(screen.getByRole("link", { name: "Đặt mật khẩu" })).toBeInTheDocument();
  });

  it("adds voice with password re-auth", async () => {
    const fetchMock = setupAccount();
    const user = userEvent.setup();
    render(<AccountView />);
    const form = await screen.findByRole("form", { name: "Đăng nhập bằng giọng nói" });
    await user.click(screen.getByRole("button", { name: "Lưu giọng nói" }));
    expect(await screen.findByText("Hãy ghi giọng nói trước khi lưu")).toBeInTheDocument();
    await user.click(within(form).getByRole("button", { name: "fake voice" }));
    await user.click(screen.getByRole("button", { name: "Lưu giọng nói" }));
    expect(await screen.findByText("Hãy nhập mật khẩu để xác nhận")).toBeInTheDocument();
    await user.type(form.querySelector("#voice-password") as HTMLInputElement, "pw-pass-1");
    await user.click(screen.getByRole("button", { name: "Lưu giọng nói" }));
    expect(await screen.findByText("Đã lưu giọng nói.")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url, init]) => url.endsWith("/me/voice") && init.method === "POST");
    const body = call?.[1].body as FormData;
    expect(body.get("password")).toBe("pw-pass-1");
    expect(body.get("audio")).toBeInstanceOf(Blob);
  });

  it("adds a webcam clip without a password when the account has none", async () => {
    const fetchMock = setupAccount({ has_password: false, google_linked: true });
    const user = userEvent.setup();
    render(<AccountView />);
    const form = await screen.findByRole("form", { name: "Đăng nhập bằng webcam (khuôn mặt)" });
    expect(form.querySelector("#webcam-password")).toBeNull();
    await user.click(within(form).getByRole("button", { name: "fake webcam" }));
    await user.click(screen.getByRole("button", { name: "Lưu webcam" }));
    expect(await screen.findByText("Đã lưu webcam.")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url, init]) => url.endsWith("/me/webcam") && init.method === "POST");
    const body = call?.[1].body as FormData;
    expect(body.has("password")).toBe(false);
    expect(body.get("video")).toBeInstanceOf(Blob);
    expect(body.has("audio")).toBe(false);
  });

  it("replaces an enabled webcam method", async () => {
    const fetchMock = setupAccount({ webcam_login: true, has_face: true, has_audio: true });
    const user = userEvent.setup();
    render(<AccountView />);
    const form = await screen.findByRole("form", { name: "Đăng nhập bằng webcam (khuôn mặt)" });
    await user.click(within(form).getByRole("button", { name: "fake webcam" }));
    await user.type(form.querySelector("#webcam-password") as HTMLInputElement, "pw-pass-1");
    await user.click(screen.getByRole("button", { name: "Thay webcam" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url, init]) => url.endsWith("/me/webcam") && init.method === "POST")).toBe(true),
    );
  });

  it("removes voice only after the password is entered", async () => {
    const fetchMock = setupAccount({ voice_login: true, webcam_login: true, has_password: true });
    const user = userEvent.setup();
    render(<AccountView />);
    const voice = await screen.findByRole("form", { name: "Đăng nhập bằng giọng nói" });
    await user.click(within(voice).getByRole("button", { name: "Hủy giọng nói" }));
    expect(await screen.findByText("Hãy nhập mật khẩu để xác nhận")).toBeInTheDocument();
    await user.type(voice.querySelector("#voice-password") as HTMLInputElement, "pw-pass-1");
    await user.click(within(voice).getByRole("button", { name: "Hủy giọng nói" }));
    await waitFor(() => {
      const del = fetchMock.mock.calls.find(([url, init]) => url.endsWith("/me/voice") && init.method === "DELETE");
      expect((del?.[1].body as FormData).get("password")).toBe("pw-pass-1");
    });
  });

  it("removes webcam without a password on a Google-only account", async () => {
    const fetchMock = setupAccount({ webcam_login: true, has_password: false, google_linked: true });
    const user = userEvent.setup();
    render(<AccountView />);
    await user.click(await screen.findByRole("button", { name: "Hủy webcam" }));
    await waitFor(() => {
      const del = fetchMock.mock.calls.find(([url, init]) => url.endsWith("/me/webcam") && init.method === "DELETE");
      expect((del?.[1].body as FormData).has("password")).toBe(false);
    });
  });

  it("shows the server message when removing the last sign-in method", async () => {
    setupAccount({ voice_login: true, has_password: false }, CONFIG, (url, init) =>
      url.endsWith("/me/voice") && init.method === "DELETE"
        ? jsonResponse({ detail: "Keep at least one sign-in method" }, 409)
        : undefined,
    );
    const user = userEvent.setup();
    render(<AccountView />);
    await user.click(await screen.findByRole("button", { name: "Hủy giọng nói" }));
    expect(await screen.findByText("Keep at least one sign-in method")).toBeInTheDocument();
  });

  it("hides voice and webcam methods when biometrics are not configured", async () => {
    setupAccount({}, { google_client_id: null, biometrics_enabled: false });
    render(<AccountView />);
    const card = await screen.findByRole("region", { name: "Các cách đăng nhập" });
    expect(card).not.toHaveTextContent("Giọng nói");
    expect(card).not.toHaveTextContent("Webcam");
  });

  it("keeps the second-factor switch off and blocked until a sample is saved", async () => {
    setupAccount({ has_audio: false, has_face: false });
    render(<AccountView />);
    const form = await screen.findByRole("form", { name: SECOND_FACTOR });
    expect(form).toHaveTextContent(/đang TẮT/);
    expect(form).toHaveTextContent(/Cần lưu ít nhất một mẫu/);
    expect(screen.getByRole("button", { name: "Bật yêu cầu xác minh sinh trắc học" })).toBeDisabled();
  });

  it("turns the second factor on after re-entering the password", async () => {
    const fetchMock = setupAccount({ has_audio: true, has_face: false });
    const user = userEvent.setup();
    render(<AccountView />);
    const form = await screen.findByRole("form", { name: SECOND_FACTOR });
    expect(screen.getByRole("heading", { name: "Bảo mật nâng cao (tùy chọn)" })).toBeInTheDocument();
    expect(form).toHaveTextContent(/webcam/);
    await user.type(form.querySelector('input[type="password"]') as HTMLInputElement, "pw-pass-1");
    await user.click(screen.getByRole("button", { name: "Bật yêu cầu xác minh sinh trắc học" }));
    await waitFor(() => {
      const put = fetchMock.mock.calls.find(([url, init]) => url.endsWith("/me/biometric-2fa") && init.method === "PUT");
      expect((put?.[1].body as FormData).get("enabled")).toBe("true");
      expect((put?.[1].body as FormData).get("password")).toBe("pw-pass-1");
    });
  });

  it("shows the second factor as on and offers to turn it off", async () => {
    setupAccount({ has_audio: true, require_biometric_2fa: true });
    render(<AccountView />);
    const form = await screen.findByRole("form", { name: SECOND_FACTOR });
    expect(form).toHaveTextContent(/đang BẬT/);
    expect(screen.getByRole("button", { name: "Tắt yêu cầu xác minh sinh trắc học" })).toBeEnabled();
  });

  it("will not unlink Google while the account has no password", async () => {
    setupAccount({ google_linked: true, has_password: false, email: "g@example.com" });
    render(<AccountView />);
    expect(await screen.findByText("Hãy đặt mật khẩu trước khi hủy liên kết Google.")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Hủy liên kết Google" })).not.toBeInTheDocument();
  });

  it("unlinks Google after re-entering the password", async () => {
    const fetchMock = setupAccount({ google_linked: true, has_password: true, email: "g@example.com" });
    const user = userEvent.setup();
    render(<AccountView />);
    const form = await screen.findByRole("form", { name: "Hủy liên kết Google" });
    await user.type(form.querySelector('input[type="password"]') as HTMLInputElement, "pw-pass-1");
    await user.click(screen.getByRole("button", { name: "Hủy liên kết Google" }));
    await waitFor(() => {
      const del = fetchMock.mock.calls.find(([url, init]) => url.endsWith("/auth/me/google") && init.method === "DELETE");
      expect(JSON.parse(del?.[1].body as string)).toEqual({ password: "pw-pass-1" });
    });
  });
});
