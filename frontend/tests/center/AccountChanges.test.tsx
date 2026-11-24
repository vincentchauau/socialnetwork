import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginFlow from "../../app/center/components/LoginFlow";
import { jsonResponse, me, mockFetch, session } from "./helpers";
import { currentTab, selectTab } from "./tabs";

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

const CONFIG = { google_client_id: null, biometrics_enabled: true, email_enabled: true, phone_enabled: false };
const NOTHING = /Chưa có thay đổi nào/;

type User = ReturnType<typeof userEvent.setup>;

function setup() {
  return mockFetch((url, init) => {
    if (url.endsWith("/auth/sessions")) return jsonResponse([]);
    if (url.endsWith("/auth/config")) return jsonResponse(CONFIG);
    if (url.endsWith("/auth/me") && (init.method ?? "GET") === "GET") return jsonResponse(me);
    if (url.endsWith("/me/password")) return jsonResponse({ ...session, csrf_token: "csrf-new" });
    if (url.endsWith("/me/username")) return jsonResponse({ ...session, username: "bob", csrf_token: "csrf-renamed" });
    return jsonResponse({});
  });
}

const callsTo = (fn: ReturnType<typeof setup>, suffix: string) => fn.mock.calls.filter(([url]) => url.endsWith(suffix));
const link = (name: string) => screen.getByRole("link", { name });
const applyButton = () => screen.getByRole("button", { name: "Đổi tài khoản" });
const summary = () => screen.getByText(/Thay đổi đang chờ|Chưa có thay đổi nào/);

async function open(): Promise<User> {
  const user = userEvent.setup();
  render(<LoginFlow />);
  await screen.findByRole("form", { name: "Đổi mật khẩu" });
  return user;
}

async function fillPassword(user: User, next = "Short-12345") {
  await user.type(screen.getByLabelText("Mật khẩu hiện tại"), "Oldpassword-1");
  await user.type(screen.getByLabelText("Mật khẩu mới"), next);
  await user.type(screen.getByLabelText("Nhập lại mật khẩu mới"), next);
}

beforeEach(() => {
  window.location.hash = "";
  goTo.mockReset();
});

describe("Đổi tài khoản button", () => {
  it("says there is nothing to apply when no tab was filled in", async () => {
    const fn = setup();
    const user = await open();
    expect(summary()).toHaveTextContent(NOTHING);
    await user.click(applyButton());
    expect(await screen.findByRole("alert")).toHaveTextContent(NOTHING);
    expect(callsTo(fn, "/me/password")).toHaveLength(0);
  });

  it("draws no apply button of its own in any tab: only Đổi tài khoản", async () => {
    setup();
    const user = await open();
    const own = ["Cập nhật mật khẩu", "Lưu giọng nói", "Thay giọng nói", "Lưu webcam", "Thay webcam", "Thêm email", "Đổi email", "Thêm số điện thoại", "Đổi số điện thoại", "Đổi tên"];
    for (const tab of ["Mật khẩu", "Webcam (khuôn mặt)", "Giọng nói", "Email"]) {
      await selectTab(user, tab);
      for (const name of own) expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    // the username form sits under the tabs, always shown, and has no apply button either
    for (const name of own) expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Đổi tên đăng nhập" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Đổi tài khoản" })).toHaveLength(1);
  });

  it("still submits a form when Enter is pressed in one of its fields", async () => {
    const fn = setup();
    const user = await open();
    await user.type(screen.getByLabelText("Mật khẩu hiện tại"), "Oldpassword-1");
    await user.type(screen.getByLabelText("Mật khẩu mới"), "Short-12345");
    await user.type(screen.getByLabelText("Nhập lại mật khẩu mới"), "Short-12345{Enter}");
    await waitFor(() => expect(callsTo(fn, "/me/password")).toHaveLength(1));
  });

  it("lists what is waiting and applies a password change", async () => {
    const fn = setup();
    const user = await open();
    await fillPassword(user);
    expect(summary()).toHaveTextContent("Thay đổi đang chờ: Mật khẩu");
    await user.click(applyButton());
    expect(await screen.findByText("Đã áp dụng 1 thay đổi.")).toBeInTheDocument();
    expect(callsTo(fn, "/me/password")).toHaveLength(1);
    // applied: the form is empty again and nothing is waiting
    await waitFor(() => expect(summary()).toHaveTextContent(NOTHING));
    expect(screen.getByLabelText("Mật khẩu mới")).toHaveValue("");
  });

  it("applies several tabs in tab order and counts them", async () => {
    const fn = setup();
    const user = await open();
    await fillPassword(user);
    await selectTab(user, "Email");
    await user.type(screen.getByLabelText("Địa chỉ email"), "ann@example.com");
    expect(summary()).toHaveTextContent("Thay đổi đang chờ: Mật khẩu, Email");
    await user.click(applyButton());
    expect(await screen.findByText("Đã áp dụng 2 thay đổi.")).toBeInTheDocument();
    expect(callsTo(fn, "/me/password")).toHaveLength(1);
    expect(callsTo(fn, "/auth/me/email")).toHaveLength(1);
  });

  it("applies a new username together with the other changes", async () => {
    const fn = setup();
    const user = await open();
    await fillPassword(user);
    // not a tab: the form sits under the tabs, always shown
    await user.type(within(screen.getByRole("form", { name: "Đổi tên đăng nhập" })).getByLabelText(/^Tên đăng nhập/), "bob");
    expect(summary()).toHaveTextContent("Thay đổi đang chờ: Mật khẩu, Tên đăng nhập");
    await user.click(applyButton());
    expect(await screen.findByText("Đã áp dụng 2 thay đổi.")).toBeInTheDocument();
    expect(callsTo(fn, "/me/password")).toHaveLength(1);
    expect(callsTo(fn, "/me/username")).toHaveLength(1);
  });

  it("applies a recorded voice sample", async () => {
    const fn = setup();
    const user = await open();
    await user.type(screen.getByLabelText("Nhập lại mật khẩu để xác nhận"), "Pw-123456!");
    await selectTab(user, "Giọng nói");
    await user.click(screen.getByRole("button", { name: "fake voice" }));
    expect(summary()).toHaveTextContent("Thay đổi đang chờ: Giọng nói");
    await user.click(applyButton());
    expect(await screen.findByText("Đã áp dụng 1 thay đổi.")).toBeInTheDocument();
    expect(callsTo(fn, "/me/voice")).toHaveLength(1);
  });

  it("stops at the first failure, opens that tab and keeps what was already applied", async () => {
    const fn = setup();
    const user = await open();
    await fillPassword(user);
    await selectTab(user, "Email");
    await user.type(screen.getByLabelText("Địa chỉ email"), "nope");
    await user.click(applyButton());
    expect(await screen.findByText(/Dừng ở "Email"/)).toHaveTextContent("Đã áp dụng 1 thay đổi trước đó.");
    expect(callsTo(fn, "/me/password")).toHaveLength(1);
    expect(callsTo(fn, "/auth/me/email")).toHaveLength(0);
    // the failing form shows its own message, in its own tab
    expect(await currentTab(user, "Cài đặt tài khoản")).toBe("Email");
    const region = screen.getByRole("region", { name: "Email" });
    expect(within(region).getByRole("alert")).toHaveTextContent("Email không hợp lệ");
  });

  it("goes to the password tab when the password change itself is rejected", async () => {
    const fn = setup();
    const user = await open();
    await selectTab(user, "Email");
    await user.type(screen.getByLabelText("Địa chỉ email"), "ann@example.com");
    await selectTab(user, "Mật khẩu");
    await fillPassword(user, "short");
    await selectTab(user, "Email");
    await user.click(applyButton());
    expect(await screen.findByText(/Dừng ở "Mật khẩu"/)).toBeInTheDocument();
    expect(await currentTab(user, "Cài đặt tài khoản")).toBe("Mật khẩu");
    expect(callsTo(fn, "/me/password")).toHaveLength(0);
    expect(callsTo(fn, "/auth/me/email")).toHaveLength(0); // later changes wait for the failed one
  });
});
