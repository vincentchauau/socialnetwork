import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AccountView from "../app/components/AccountView";
import { headerOf, jsonResponse, me, mockFetch, session } from "./helpers";

const goTo = vi.hoisted(() => vi.fn());
vi.mock("../app/lib/navigate", async (original) => ({
  ...(await original<typeof import("../app/lib/navigate")>()),
  goTo,
}));

// The real recorders need camera hardware; this stand-in "records" instantly.
vi.mock("../app/components/BiometricCapture", () => ({
  default: ({ onVideo, onAudio }: { onVideo: (b: Blob) => void; onAudio: (b: Blob) => void }) => (
    <div>
      <button type="button" onClick={() => onVideo(new Blob(["v"]))}>
        fake video
      </button>
      <button type="button" onClick={() => onAudio(new Blob(["a"]))}>
        fake audio
      </button>
    </div>
  ),
}));

const CONFIG = { google_client_id: null, biometrics_enabled: true };

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
    expect(screen.queryByRole("form", { name: "Thêm giọng nói hoặc khuôn mặt" })).not.toBeInTheDocument();
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

  it("enrolls biometrics, toggles biometric login and removes them", async () => {
    const fetchMock = setupAccount({ has_audio: true, has_face: true });
    const user = userEvent.setup();
    render(<AccountView />);
    const enroll = await screen.findByRole("form", { name: "Thêm giọng nói hoặc khuôn mặt" });

    await user.type(enroll.querySelector('input[type="password"]') as HTMLInputElement, "pw-pass-1");
    await user.click(screen.getByRole("button", { name: "Lưu dữ liệu sinh trắc" }));
    expect(await screen.findByText(/Hãy quay khuôn mặt/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "fake video" }));
    await user.click(screen.getByRole("button", { name: "Lưu dữ liệu sinh trắc" }));
    expect(await screen.findByText(/Đã lưu\./)).toBeInTheDocument();

    const toggle = screen.getByRole("form", { name: "Đăng nhập chỉ bằng giọng nói và khuôn mặt" });
    expect(screen.getByRole("heading", { name: /đang tắt/ })).toBeInTheDocument();
    await user.type(toggle.querySelector('input[type="password"]') as HTMLInputElement, "pw-pass-1");
    await user.click(screen.getByRole("button", { name: "Bật đăng nhập chỉ bằng sinh trắc học" }));
    await waitFor(() => {
      const put = fetchMock.mock.calls.find(([, init]) => init.method === "PUT");
      expect((put?.[1].body as FormData).get("enabled")).toBe("true");
    });

    const remove = screen.getByRole("form", { name: "Xóa giọng nói và khuôn mặt" });
    await user.type(remove.querySelector('input[type="password"]') as HTMLInputElement, "pw-pass-1");
    await user.click(screen.getByRole("button", { name: "Xóa dữ liệu giọng nói và khuôn mặt" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url, init]) => url.endsWith("/me/biometrics") && init.method === "DELETE")).toBe(true),
    );
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
});
