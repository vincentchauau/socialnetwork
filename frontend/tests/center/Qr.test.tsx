import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LoginFlow from "../../app/center/components/LoginFlow";
import QrApproveView from "../../app/center/components/QrApproveView";
import { QR_POLL_MS } from "../../app/center/components/QrLogin";
import { parseFragmentParam } from "../../app/center/hooks/useUrlToken";
import * as qrPage from "../../app/center/user/qr/page";
import { jsonResponse, me, mockFetch, session } from "./helpers";
import { selectTab } from "./tabs";

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

const CONFIG = { google_client_id: null, biometrics_enabled: false, email_enabled: false };
const START = {
  request_id: "rid1",
  poll_token: "pt1",
  verify_code: "AB12",
  expires_in: 60,
  qr_url: "https://sn.test/login/qr#r=rid1",
};
const INSTRUCTIONS =
  "Mở Mạng xã hội trên điện thoại đã đăng nhập, quét mã này, đối chiếu mã xác nhận rồi bấm Cho phép";

type Handler = (url: string, init: RequestInit) => Response | Promise<Response> | undefined;
type User = ReturnType<typeof userEvent.setup>;

const pending = () => jsonResponse({ status: "pending" });

function setup(poll: Handler = () => pending(), extra?: Handler) {
  let started = 0;
  return mockFetch((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/config")) return jsonResponse(CONFIG);
    if (url.endsWith("/auth/qr/start")) {
      started += 1;
      return jsonResponse({ ...START, request_id: `rid${started}`, verify_code: started === 1 ? "AB12" : "ZZ99" }, 201);
    }
    if (url.endsWith("/auth/qr/poll")) return poll(url, init) ?? pending();
    return jsonResponse({ detail: "unexpected " + url }, 500);
  });
}

const callsTo = (fn: ReturnType<typeof setup>, suffix: string) => fn.mock.calls.filter(([url]) => url.endsWith(suffix));

async function openQr(user: User) {
  await selectTab(user, "Mã QR");
  await screen.findByText(/Mã xác nhận: /);
}

/** Advances in 1 s steps so each countdown tick can re-render and schedule the next one. */
async function advance(ms: number) {
  for (let left = ms; left > 0; left -= 1000) await act(async () => void (await vi.advanceTimersByTimeAsync(Math.min(1000, left))));
}

beforeEach(() => {
  goTo.mockReset();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  window.history.replaceState({}, "", "/user");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("QR sign-in tab (desktop)", () => {
  it("starts a request and shows the QR, the big code, the instructions and a countdown", async () => {
    const fn = setup();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await openQr(user);
    expect(JSON.parse(String(callsTo(fn, "/auth/qr/start")[0][1].body))).toEqual({});
    expect(screen.getByText("Mã xác nhận: AB12")).toBeInTheDocument();
    expect(screen.getByText(INSTRUCTIONS)).toBeInTheDocument();
    const image = await screen.findByAltText("Mã QR để đăng nhập bằng điện thoại");
    expect(image.getAttribute("src")).toMatch(/^data:image\/svg\+xml/);
    expect(screen.getByRole("timer")).toHaveTextContent("60 giây");
    await advance(3000);
    expect(screen.getByRole("timer")).toHaveTextContent("57 giây");
    expect(fn.mock.calls.every(([url]) => !url.includes("sn.test"))).toBe(true); // QR drawn client-side
  });

  it("polls every 2 seconds with the request id and token", async () => {
    const fn = setup();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await openQr(user);
    expect(callsTo(fn, "/auth/qr/poll")).toHaveLength(0);
    await advance(QR_POLL_MS);
    expect(callsTo(fn, "/auth/qr/poll")).toHaveLength(1);
    expect(JSON.parse(String(callsTo(fn, "/auth/qr/poll")[0][1].body))).toEqual({ request_id: "rid1", poll_token: "pt1" });
    await advance(QR_POLL_MS * 2);
    expect(callsTo(fn, "/auth/qr/poll")).toHaveLength(3);
  });

  it("never overlaps polls: the next one waits for the previous response", async () => {
    let release: (response: Response) => void = () => undefined;
    const slow = new Promise<Response>((resolve) => (release = resolve));
    let n = 0;
    const fn = setup(() => (++n === 1 ? slow : pending()));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await openQr(user);
    await advance(QR_POLL_MS);
    await advance(QR_POLL_MS * 5);
    expect(callsTo(fn, "/auth/qr/poll")).toHaveLength(1);
    release(pending());
    await advance(QR_POLL_MS);
    expect(callsTo(fn, "/auth/qr/poll")).toHaveLength(2);
  });

  it("stops polling when the tab changes", async () => {
    const fn = setup();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await openQr(user);
    await advance(QR_POLL_MS);
    await selectTab(user, "Mật khẩu");
    const seen = callsTo(fn, "/auth/qr/poll").length;
    await advance(QR_POLL_MS * 5);
    expect(callsTo(fn, "/auth/qr/poll")).toHaveLength(seen);
  });

  it("stops polling on unmount, even with a request in flight, and never signs in afterwards", async () => {
    let release: (response: Response) => void = () => undefined;
    const slow = new Promise<Response>((resolve) => (release = resolve));
    const fn = setup(() => slow);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const view = render(<LoginFlow />);
    await openQr(user);
    await advance(QR_POLL_MS);
    view.unmount();
    release(jsonResponse(session));
    await advance(QR_POLL_MS * 5);
    expect(callsTo(fn, "/auth/qr/poll")).toHaveLength(1);
    expect(goTo).not.toHaveBeenCalled();
  });

  it("signs in when the phone approves (session body) and goes to the next page", async () => {
    let n = 0;
    setup(() => (++n < 3 ? pending() : jsonResponse(session)));
    window.history.replaceState({}, "", "/user?next=/user");
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await openQr(user);
    await advance(QR_POLL_MS * 3);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/user"));
  });

  it("reuses the MFA step when the approved login needs a second factor", async () => {
    setup(() => jsonResponse({ mfa_required: true, mfa_token: "mt", factors: ["totp"] }));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await openQr(user);
    await advance(QR_POLL_MS);
    expect(await screen.findByRole("heading", { name: "Xác minh danh tính" })).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
  });

  it("keeps a way to start over once the approved sign-in has been handed off", async () => {
    setup(() => jsonResponse(session));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await openQr(user);
    await advance(QR_POLL_MS);
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(await screen.findByRole("button", { name: "Tạo mã mới" })).toBeInTheDocument();
  });

  it("shows denied, stops polling and creates a new code on demand", async () => {
    let denied = true;
    const fn = setup(() => (denied ? jsonResponse({ status: "denied" }) : pending()));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await openQr(user);
    await advance(QR_POLL_MS);
    expect(await screen.findByText("Yêu cầu đăng nhập đã bị từ chối trên điện thoại")).toBeInTheDocument();
    expect(screen.queryByText("Mã xác nhận: AB12")).not.toBeInTheDocument();
    await advance(QR_POLL_MS * 4);
    expect(callsTo(fn, "/auth/qr/poll")).toHaveLength(1);
    denied = false;
    await user.click(screen.getByRole("button", { name: "Tạo mã mới" }));
    expect(await screen.findByText("Mã xác nhận: ZZ99")).toBeInTheDocument();
    await advance(QR_POLL_MS);
    expect(JSON.parse(String(callsTo(fn, "/auth/qr/poll")[1][1].body)).request_id).toBe("rid2");
  });

  it("shows expired when the server says so", async () => {
    setup(() => jsonResponse({ status: "expired" }));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await openQr(user);
    await advance(QR_POLL_MS);
    expect(await screen.findByText("Mã QR đã hết hạn")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tạo mã mới" })).toBeInTheDocument();
  });

  it("expires locally when the countdown ends and stops polling", async () => {
    const fn = mockFetch((url) => {
      if (url.endsWith("/auth/config")) return jsonResponse(CONFIG);
      if (url.endsWith("/auth/me") || url.endsWith("/auth/refresh")) return jsonResponse({ detail: "no" }, 401); // signed out: the page opens on the sign-in form
      if (url.endsWith("/auth/qr/start")) return jsonResponse({ ...START, expires_in: 3 }, 201);
      return pending();
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await openQr(user);
    await advance(3500);
    expect(await screen.findByText("Mã QR đã hết hạn")).toBeInTheDocument();
    const seen = callsTo(fn as ReturnType<typeof setup>, "/auth/qr/poll").length;
    await advance(QR_POLL_MS * 5);
    expect(callsTo(fn as ReturnType<typeof setup>, "/auth/qr/poll")).toHaveLength(seen);
  });

  it("treats a 404 on poll as expired but keeps polling through transient errors", async () => {
    let n = 0;
    const fn = setup(() => {
      n += 1;
      if (n === 1) return jsonResponse({ detail: "boom" }, 500);
      if (n === 2) return jsonResponse({ detail: "slow down" }, 429);
      return jsonResponse({ detail: "gone" }, 404);
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await openQr(user);
    await advance(QR_POLL_MS * 3);
    expect(await screen.findByText("Mã QR đã hết hạn")).toBeInTheDocument();
    expect(callsTo(fn, "/auth/qr/poll")).toHaveLength(3);
  });

  it("shows an error with a retry when the request cannot be created", async () => {
    let fail = true;
    setup(undefined, (url) => (url.endsWith("/auth/qr/start") && fail ? jsonResponse({ detail: "Không tạo được" }, 500) : undefined));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await selectTab(user, "Mã QR");
    expect(await screen.findByText("Không tạo được")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Tạo mã mới" }));
    expect(await screen.findByText("Mã xác nhận: AB12")).toBeInTheDocument();
  });

  it("ignores a start response that arrives after the tab was left", async () => {
    let release: (response: Response) => void = () => undefined;
    const slow = new Promise<Response>((resolve) => (release = resolve));
    const fn = setup(undefined, (url) => (url.endsWith("/auth/qr/start") ? slow : undefined));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await selectTab(user, "Mã QR");
    expect(screen.getByText("Đang tạo mã QR...")).toBeInTheDocument();
    await selectTab(user, "Mật khẩu");
    release(jsonResponse(START, 201));
    await advance(QR_POLL_MS * 3);
    expect(callsTo(fn, "/auth/qr/poll")).toHaveLength(0);
  });

  it("ignores a failed start that arrives after the tab was left", async () => {
    let release: (response: Response) => void = () => undefined;
    const slow = new Promise<Response>((resolve) => (release = resolve));
    setup(undefined, (url) => (url.endsWith("/auth/qr/start") ? slow : undefined));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await selectTab(user, "Mã QR");
    await selectTab(user, "Mật khẩu");
    release(jsonResponse({ detail: "x" }, 500));
    await advance(100);
    expect(screen.queryByText("x")).not.toBeInTheDocument();
  });
});

describe("parseFragmentParam", () => {
  it("reads only the fragment", () => {
    expect(parseFragmentParam("#r=abc", "r")).toBe("abc");
    expect(parseFragmentParam("r=abc&x=1", "r")).toBe("abc");
    expect(parseFragmentParam("", "r")).toBeNull();
    expect(parseFragmentParam("#x=1", "r")).toBeNull();
  });
});

describe("/user/qr page shell", () => {
  it("renders the approval view and sends no referrer", () => {
    expect(qrPage.metadata).toEqual({ referrer: "no-referrer" });
    setup();
    render(<qrPage.default />);
    expect(screen.getByRole("heading", { name: "Đăng nhập bằng mã QR" })).toBeInTheDocument();
  });
});

const DETAILS = {
  verify_code: "AB12",
  requester_ip: "203.0.113.9",
  requester_user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
  created_at: "2030-01-01T10:00:00Z",
  expires_in: 120,
};

function phoneSetup(routes: Handler = () => undefined, signedIn = true) {
  return mockFetch((url, init) => {
    const custom = routes(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/me")) return signedIn ? jsonResponse(me) : jsonResponse({ detail: "no" }, 401);
    if (url.endsWith("/auth/refresh")) return jsonResponse({ detail: "no" }, 401);
    if (url.endsWith("/auth/qr/rid1")) return jsonResponse(DETAILS);
    if (url.endsWith("/auth/qr/rid1/approve") || url.endsWith("/auth/qr/rid1/deny")) return jsonResponse({ ok: true });
    return jsonResponse({ detail: "unexpected " + url }, 500);
  });
}

async function openApproval(hash = "#r=rid1") {
  window.history.replaceState({}, "", `/user/qr${hash}`);
  render(<QrApproveView />);
}

describe("QR approval page (phone)", () => {
  beforeEach(() => vi.useRealTimers());

  it("explains a missing request id and clears nothing it should not", async () => {
    const fn = phoneSetup();
    await openApproval("");
    expect(await screen.findByText(/Liên kết không hợp lệ/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Về trang đăng nhập" })).toHaveAttribute("href", "/user");
    expect(fn).not.toHaveBeenCalled();
  });

  it("asks a signed-out visitor to sign in first and links to /login", async () => {
    const fn = phoneSetup(() => undefined, false);
    await openApproval();
    expect(await screen.findByText(/Bạn cần đăng nhập trên điện thoại này trước/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Đăng nhập" })).toHaveAttribute("href", "/user");
    expect(fn.mock.calls.some(([url]) => url.includes("/auth/qr/rid1"))).toBe(false);
  });

  it("reads the id from the fragment, clears it and shows the requesting device", async () => {
    const fn = phoneSetup();
    await openApproval("#r=rid1");
    expect(await screen.findByText("Thiết bị đang yêu cầu đăng nhập", { selector: "h2" })).toBeInTheDocument();
    expect(screen.getByText("Chrome trên Windows")).toBeInTheDocument();
    expect(screen.getByText("Địa chỉ IP: 203.0.113.9")).toBeInTheDocument();
    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/user/qr");
    expect(fn.mock.calls.every(([url]) => !url.includes("#"))).toBe(true);
    // the typed code, not the server's, is what the phone must send: the details do not prefill it
    expect(screen.getByLabelText(/Mã xác nhận hiển thị/)).toHaveValue("");
  });

  it("shows an unknown device and IP gracefully", async () => {
    phoneSetup((url) =>
      url.endsWith("/auth/qr/rid1") ? jsonResponse({ ...DETAILS, requester_ip: null, requester_user_agent: null }) : undefined,
    );
    await openApproval();
    expect(await screen.findByText("Thiết bị không rõ")).toBeInTheDocument();
    expect(screen.getByText("Địa chỉ IP: không rõ")).toBeInTheDocument();
  });

  it("approves with the typed (upper-cased) code", async () => {
    const fn = phoneSetup();
    const user = userEvent.setup();
    await openApproval();
    await user.type(await screen.findByLabelText(/Mã xác nhận hiển thị/), "ab12");
    await user.click(screen.getByRole("button", { name: "Cho phép" }));
    expect(await screen.findByText("Đã cho phép đăng nhập trên thiết bị kia.")).toBeInTheDocument();
    const call = fn.mock.calls.find(([url]) => url.endsWith("/auth/qr/rid1/approve"))!;
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(String(call[1].body))).toEqual({ verify_code: "AB12" });
    expect(screen.queryByRole("button", { name: "Cho phép" })).not.toBeInTheDocument();
  });

  it("asks for the whole code before calling the server", async () => {
    const fn = phoneSetup();
    const user = userEvent.setup();
    await openApproval();
    await user.type(await screen.findByLabelText(/Mã xác nhận hiển thị/), "AB");
    await user.click(screen.getByRole("button", { name: "Cho phép" }));
    expect(await screen.findByText("Hãy nhập mã xác nhận gồm 4 ký tự")).toBeInTheDocument();
    expect(fn.mock.calls.some(([url]) => url.endsWith("/approve"))).toBe(false);
  });

  it.each([401, 403, 422])("says the code is wrong on a %i and allows another try", async (status) => {
    let wrong = true;
    phoneSetup((url) =>
      url.endsWith("/approve") ? (wrong ? jsonResponse({ detail: "nope" }, status) : jsonResponse({ ok: true })) : undefined,
    );
    const user = userEvent.setup();
    await openApproval();
    await user.type(await screen.findByLabelText(/Mã xác nhận hiển thị/), "ZZZZ");
    await user.click(screen.getByRole("button", { name: "Cho phép" }));
    expect(await screen.findByText("Mã xác nhận không đúng")).toBeInTheDocument();
    wrong = false;
    await user.click(screen.getByRole("button", { name: "Cho phép" }));
    expect(await screen.findByText("Đã cho phép đăng nhập trên thiết bị kia.")).toBeInTheDocument();
  });

  it("says the request expired on a 404 while approving", async () => {
    phoneSetup((url) => (url.endsWith("/approve") ? jsonResponse({ detail: "Not found" }, 404) : undefined));
    const user = userEvent.setup();
    await openApproval();
    await user.type(await screen.findByLabelText(/Mã xác nhận hiển thị/), "AB12");
    await user.click(screen.getByRole("button", { name: "Cho phép" }));
    expect(await screen.findByText("Yêu cầu đã hết hạn")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cho phép" })).not.toBeInTheDocument();
  });

  it("shows other approval errors as they are (429)", async () => {
    phoneSetup((url) => (url.endsWith("/approve") ? jsonResponse({ detail: "x" }, 429) : undefined));
    const user = userEvent.setup();
    await openApproval();
    await user.type(await screen.findByLabelText(/Mã xác nhận hiển thị/), "AB12");
    await user.click(screen.getByRole("button", { name: "Cho phép" }));
    expect(await screen.findByText("Thử quá nhiều lần, hãy thử lại sau")).toBeInTheDocument();
  });

  it("denies the request", async () => {
    const fn = phoneSetup();
    const user = userEvent.setup();
    await openApproval();
    await user.click(await screen.findByRole("button", { name: "Từ chối" }));
    expect(await screen.findByText("Đã từ chối yêu cầu đăng nhập.")).toBeInTheDocument();
    const call = fn.mock.calls.find(([url]) => url.endsWith("/auth/qr/rid1/deny"))!;
    expect(call[1].method).toBe("POST");
  });

  it("says the request expired when denying a vanished request", async () => {
    phoneSetup((url) => (url.endsWith("/deny") ? jsonResponse({ detail: "x" }, 404) : undefined));
    const user = userEvent.setup();
    await openApproval();
    await user.click(await screen.findByRole("button", { name: "Từ chối" }));
    expect(await screen.findByText("Yêu cầu đã hết hạn")).toBeInTheDocument();
  });

  it("shows the server error when denying fails", async () => {
    phoneSetup((url) => (url.endsWith("/deny") ? jsonResponse({ detail: "Lỗi máy chủ" }, 500) : undefined));
    const user = userEvent.setup();
    await openApproval();
    await user.click(await screen.findByRole("button", { name: "Từ chối" }));
    expect(await screen.findByText("Lỗi máy chủ")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cho phép" })).toBeInTheDocument();
  });

  it("says the request expired when the details are gone (404/410)", async () => {
    phoneSetup((url) => (url.endsWith("/auth/qr/rid1") ? jsonResponse({ detail: "Not found" }, 410) : undefined));
    await openApproval();
    expect(await screen.findByText("Yêu cầu đã hết hạn")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Về trang chủ" })).toHaveAttribute("href", "/");
  });

  it("shows a load error that is not a wrong-code message", async () => {
    phoneSetup((url) => (url.endsWith("/auth/qr/rid1") ? jsonResponse({ detail: "Lỗi tải" }, 403) : undefined));
    await openApproval();
    expect(await screen.findByText("Lỗi tải")).toBeInTheDocument();
  });

  it("shows an error when the session check itself fails", async () => {
    phoneSetup((url) => (url.endsWith("/auth/me") ? jsonResponse({ detail: "Máy chủ lỗi" }, 500) : undefined));
    await openApproval();
    expect(await screen.findByText("Máy chủ lỗi")).toBeInTheDocument();
  });

  it("does nothing when unmounted before the details arrive", async () => {
    let release: (response: Response) => void = () => undefined;
    const slow = new Promise<Response>((resolve) => (release = resolve));
    phoneSetup((url) => (url.endsWith("/auth/qr/rid1") ? slow : undefined));
    window.history.replaceState({}, "", "/user/qr#r=rid1");
    const view = render(<QrApproveView />);
    await waitFor(() => expect(window.location.hash).toBe(""));
    view.unmount();
    release(jsonResponse(DETAILS));
    await Promise.resolve();
    await waitFor(() => expect(document.body).not.toHaveTextContent("Thiết bị đang yêu cầu"));
  });
});
