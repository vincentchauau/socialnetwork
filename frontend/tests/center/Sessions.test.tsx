import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { setCsrfToken } from "@sn/api";
import SessionsMethod, { describeDevice, formatWhen } from "../../app/center/components/SessionsMethod";
import * as auth from "../../app/center/lib/auth";
import { jsonResponse, mockFetch } from "./helpers";

const CHROME_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36";
const SAFARI_IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile Safari/604.1";

const NOW = "2025-03-04T10:20:30Z";
const row = (id: number, extra: Partial<auth.DeviceSession> = {}): auth.DeviceSession => ({
  id,
  current: false,
  created_at: NOW,
  last_seen_at: NOW,
  ip: "10.0.0.1",
  user_agent: CHROME_WIN,
  method: "password",
  ...extra,
});

function sessions(initial: auth.DeviceSession[], extra?: (url: string, init: RequestInit) => Response | undefined) {
  const state = { items: initial, deleted: [] as number[], others: 0 };
  const fn = mockFetch((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/sessions") && (init.method ?? "GET") === "GET") return jsonResponse(state.items);
    if (url.endsWith("/revoke-others")) {
      const revoked = state.items.filter((item) => !item.current);
      state.items = state.items.filter((item) => item.current);
      state.others += 1;
      return jsonResponse({ revoked: revoked.length });
    }
    const match = /\/auth\/sessions\/(\d+)$/.exec(url);
    if (match && init.method === "DELETE") {
      state.deleted.push(Number(match[1]));
      state.items = state.items.filter((item) => item.id !== Number(match[1]));
      return jsonResponse(null, 204);
    }
    return jsonResponse({ detail: "unexpected" }, 500);
  });
  return { fn, state };
}

beforeEach(() => setCsrfToken(null));

describe("describeDevice", () => {
  it.each([
    [CHROME_WIN, "Chrome trên Windows"],
    [SAFARI_IPHONE, "Safari trên iOS"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) Gecko Firefox/120.0", "Firefox trên macOS"],
    ["Mozilla/5.0 (Linux; Android 14) Chrome/120 Mobile Safari/537 Edg/120", "Edge trên Android"],
    ["Opera OPR/90 (X11; CrOS x86_64)", "Opera trên ChromeOS"],
    ["Mozilla/5.0 (X11; Linux x86_64)", "Linux"],
    ["Safari/605", "Safari"],
    ["  curl/8.0  ", "curl/8.0"],
    ["x".repeat(80), `${"x".repeat(60)}…`],
    ["", "Thiết bị không rõ"],
    [null, "Thiết bị không rõ"],
  ])("%j -> %s", (agent, label) => {
    expect(describeDevice(agent)).toBe(label);
  });

  it("formatWhen returns a local time or the raw text when unparsable", () => {
    expect(formatWhen(NOW)).toBe(new Date(NOW).toLocaleString("vi-VN"));
    expect(formatWhen("hôm qua")).toBe("hôm qua");
  });
});

describe("session helpers", () => {
  it("call the documented endpoints", async () => {
    const fn = mockFetch((url) => (url.endsWith("/revoke-others") ? jsonResponse({ revoked: 2 }) : jsonResponse(null, 204)));
    await auth.revokeSession(5);
    expect(await auth.revokeOtherSessions()).toEqual({ revoked: 2 });
    expect(fn.mock.calls[0][0]).toBe("/api/center/auth/sessions/5");
    expect(fn.mock.calls[0][1].method).toBe("DELETE");
    expect(fn.mock.calls[1][1].method).toBe("POST");
  });
});

describe("SessionsMethod", () => {
  it("lists devices with the current-session badge, method, IP and times", async () => {
    sessions([
      row(1, { current: true, method: "passkey" }),
      row(2, { user_agent: SAFARI_IPHONE, method: "google", ip: null }),
      row(3, { user_agent: null, method: "mystery" }),
    ]);
    render(<SessionsMethod />);
    const list = await screen.findByRole("list", { name: "Phiên đăng nhập đang hoạt động" });
    const [current, other, unknown] = within(list).getAllByRole("listitem");
    expect(within(current).getByText("Phiên này")).toBeInTheDocument();
    expect(within(current).getByText("Chrome trên Windows")).toBeInTheDocument();
    expect(within(current).getByText(/Đăng nhập bằng Passkey · IP 10\.0\.0\.1/)).toBeInTheDocument();
    expect(within(current).getByText(new RegExp(`Bắt đầu ${formatWhen(NOW).replace(/[/.]/g, "\\$&")}`))).toBeInTheDocument();
    expect(within(current).queryByRole("button")).toBeNull();
    expect(within(other).queryByText("Phiên này")).toBeNull();
    expect(within(other).getByText("Safari trên iOS")).toBeInTheDocument();
    expect(within(other).getByText(/Google · IP không rõ/)).toBeInTheDocument();
    expect(within(unknown).getByText("Thiết bị không rõ")).toBeInTheDocument();
    expect(within(unknown).getByText(/Đăng nhập bằng mystery/)).toBeInTheDocument();
  });

  it("shows loading, then an empty state without the revoke-others button", async () => {
    sessions([]);
    render(<SessionsMethod />);
    expect(screen.getByRole("status")).toHaveTextContent("Đang tải...");
    expect(await screen.findByText("Không có phiên đăng nhập nào.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /tất cả thiết bị khác/ })).toBeNull();
  });

  it("offers no revoke-others button when only the current session exists", async () => {
    sessions([row(1, { current: true })]);
    render(<SessionsMethod />);
    await screen.findByText("Phiên này");
    expect(screen.queryByRole("button", { name: /tất cả thiết bị khác/ })).toBeNull();
  });

  it("shows a load error and retries", async () => {
    let fail = true;
    sessions([row(1, { current: true })], (url) =>
      url.endsWith("/auth/sessions") && fail ? jsonResponse({ detail: "Máy chủ lỗi" }, 500) : undefined,
    );
    const user = userEvent.setup();
    render(<SessionsMethod />);
    expect(await screen.findByText("Máy chủ lỗi")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByText("Phiên này")).toBeInTheDocument();
  });

  it("treats a non-list reply as an error", async () => {
    sessions([], (url) => (url.endsWith("/auth/sessions") ? jsonResponse({ nope: true }) : undefined));
    render(<SessionsMethod />);
    expect(await screen.findByText("Không tải được danh sách thiết bị")).toBeInTheDocument();
  });

  it("revokes one other device after an inline confirmation", async () => {
    const { state } = sessions([row(1, { current: true }), row(2, { user_agent: SAFARI_IPHONE })]);
    const user = userEvent.setup();
    render(<SessionsMethod />);
    await user.click(await screen.findByRole("button", { name: "Đăng xuất thiết bị" }));
    const form = screen.getByRole("form", { name: "Đăng xuất thiết bị Safari trên iOS" });
    expect(state.deleted).toEqual([]);
    await user.click(within(form).getByRole("button", { name: "Xác nhận đăng xuất" }));
    await waitFor(() => expect(state.deleted).toEqual([2]));
    await waitFor(() => expect(screen.queryByText("Safari trên iOS")).toBeNull());
    expect(screen.getByText("Phiên này")).toBeInTheDocument();
  });

  it("can cancel the confirmation without revoking", async () => {
    const { state } = sessions([row(1, { current: true }), row(2)]);
    const user = userEvent.setup();
    render(<SessionsMethod />);
    await user.click(await screen.findByRole("button", { name: "Đăng xuất thiết bị" }));
    await user.click(screen.getByRole("button", { name: "Hủy" }));
    expect(screen.getByRole("button", { name: "Đăng xuất thiết bị" })).toBeInTheDocument();
    expect(state.deleted).toEqual([]);
  });

  it("shows the error when revoking a device fails and keeps the row", async () => {
    sessions([row(1, { current: true }), row(2)], (url, init) =>
      init.method === "DELETE" ? jsonResponse({ detail: "Không thể đăng xuất" }, 500) : undefined,
    );
    const user = userEvent.setup();
    render(<SessionsMethod />);
    await user.click(await screen.findByRole("button", { name: "Đăng xuất thiết bị" }));
    await user.click(screen.getByRole("button", { name: "Xác nhận đăng xuất" }));
    expect(await screen.findByText("Không thể đăng xuất")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Xác nhận đăng xuất" })).toBeInTheDocument();
  });

  it("signs out all other devices and reports how many", async () => {
    const { state } = sessions([row(1, { current: true }), row(2), row(3)]);
    const user = userEvent.setup();
    render(<SessionsMethod />);
    await user.click(await screen.findByRole("button", { name: "Đăng xuất tất cả thiết bị khác" }));
    expect(await screen.findByText("Đã đăng xuất 2 thiết bị")).toBeInTheDocument();
    expect(state.others).toBe(1);
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(1));
    expect(screen.queryByRole("button", { name: /tất cả thiết bị khác/ })).toBeNull();
  });

  it("shows the error when signing out the others fails", async () => {
    sessions([row(1, { current: true }), row(2)], (url) =>
      url.endsWith("/revoke-others") ? jsonResponse({ detail: "Thử lại sau" }, 429) : undefined,
    );
    const user = userEvent.setup();
    render(<SessionsMethod />);
    await user.click(await screen.findByRole("button", { name: "Đăng xuất tất cả thiết bị khác" }));
    expect(await screen.findByText("Thử quá nhiều lần, hãy thử lại sau")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});
