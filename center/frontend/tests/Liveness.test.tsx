import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BiometricMethod from "../app/components/BiometricMethod";
import LoginFlow from "../app/components/LoginFlow";
import MagicLoginView from "../app/components/MagicLoginView";
import VideoRecord from "../app/components/VideoRecord";
import { RECORD_MS } from "../app/hooks/useMediaRecorder";
import { jsonResponse, mockFetch, session } from "./helpers";

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

vi.mock("../app/components/GoogleSignInButton", () => ({ default: () => null }));

const CHALLENGE = { challenge_token: "lv-token", actions: ["blink", "turn_left"], expires_in: 60 };
const BASE = { google_client_id: null, biometrics_enabled: true, email_enabled: false };
const ON = { ...BASE, liveness_enabled: true, liveness_required: false };
const REQUIRED = { ...BASE, liveness_enabled: true, liveness_required: true };
const OFF = { ...BASE, liveness_enabled: false, liveness_required: false };

const stream = { getTracks: () => [{ stop: vi.fn() }] };
const recorders: unknown[] = [];

class FakeRecorder {
  state = "inactive";
  mimeType = "video/webm";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public readonly source: unknown) {
    recorders.push(source);
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["x".repeat(2048)]) });
    this.onstop?.();
  }
}

type Handler = (url: string, init: RequestInit) => Response | undefined;
type User = ReturnType<typeof userEvent.setup>;

function setup(config: unknown, extra?: Handler) {
  return mockFetch((url, init) => {
    const custom = extra?.(url, init);
    if (custom) return custom;
    if (url.endsWith("/auth/config")) return jsonResponse(config);
    if (url.endsWith("/liveness/challenge")) return jsonResponse(CHALLENGE, 201);
    if (url.endsWith("/login/webcam") || url.endsWith("/login/biometric") || url.endsWith("/me/webcam")) return jsonResponse(session);
    if (url.endsWith("/auth/login")) return jsonResponse({ mfa_required: true, mfa_token: "mt", factors: ["biometric"] });
    if (url.endsWith("/email/login/magic")) return jsonResponse({ mfa_required: true, mfa_token: "mt", factors: ["biometric"] });
    if (url.endsWith("/register/combined")) return jsonResponse(session, 201);
    return jsonResponse({ detail: "unexpected " + url }, 500);
  });
}

const callsTo = (fn: ReturnType<typeof setup>, suffix: string) => fn.mock.calls.filter(([url]) => url.endsWith(suffix));
const formOf = (fn: ReturnType<typeof setup>, suffix: string) => callsTo(fn, suffix)[0][1].body as FormData;

async function elapse(ms: number) {
  await act(async () => void (await vi.advanceTimersByTimeAsync(ms)));
}

async function recordClip(user: User, name: RegExp = /^Quay khuôn mặt$/) {
  await user.click(screen.getByRole("button", { name }));
  await screen.findByRole("button", { name: /Đang quay/ });
  await elapse(RECORD_MS);
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  goTo.mockReset();
  recorders.length = 0;
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
  });
  URL.createObjectURL = vi.fn(() => "blob:x");
  URL.revokeObjectURL = vi.fn();
  window.history.replaceState({}, "", "/login");
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("VideoRecord with liveness", () => {
  it("fetches the challenge only when recording starts, then shows the steps one by one", async () => {
    const fn = setup(ON);
    const onRecorded = vi.fn();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<VideoRecord liveness={ON} onRecorded={onRecorded} />);
    expect(callsTo(fn, "/liveness/challenge")).toHaveLength(0); // fetched right before recording, not on mount
    await user.click(screen.getByRole("button", { name: "Quay khuôn mặt" }));
    await screen.findByRole("button", { name: /Đang quay/ });
    expect(JSON.parse(String(callsTo(fn, "/liveness/challenge")[0][1].body))).toEqual({});
    const steps = screen.getByTestId("liveness-steps");
    expect(steps).toHaveTextContent("Bước 1/2: Nháy mắt");
    expect(within(steps).getByText("2. Quay mặt sang trái")).toBeInTheDocument();
    await elapse(RECORD_MS / 2);
    expect(screen.getByTestId("liveness-steps")).toHaveTextContent("Bước 2/2: Quay mặt sang trái");
    await elapse(RECORD_MS / 2);
    expect(screen.queryByTestId("liveness-steps")).not.toBeInTheDocument();
    expect(onRecorded).toHaveBeenCalledTimes(1);
    expect(onRecorded.mock.calls[0][1]).toBe("lv-token");
  });

  it.each([
    ["turn_right", "Quay mặt sang phải"],
    ["open_mouth", "Há miệng"],
  ])("labels %s as %s and skips unknown actions", async (action, label) => {
    setup(ON, (url) =>
      url.endsWith("/liveness/challenge")
        ? jsonResponse({ ...CHALLENGE, actions: [action, "dance"] }, 201)
        : undefined,
    );
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<VideoRecord liveness={ON} onRecorded={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Quay khuôn mặt" }));
    await screen.findByRole("button", { name: /Đang quay/ });
    expect(screen.getByTestId("liveness-steps")).toHaveTextContent(`Bước 1/1: ${label}`);
    expect(screen.queryByText(/dance/)).not.toBeInTheDocument();
  });

  it("does not ask for a challenge when liveness is disabled or not configured", async () => {
    const fn = setup(OFF);
    const onRecorded = vi.fn();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { rerender } = render(<VideoRecord liveness={OFF} onRecorded={onRecorded} />);
    await recordClip(user);
    rerender(<VideoRecord onRecorded={onRecorded} />);
    await recordClip(user);
    expect(callsTo(fn, "/liveness/challenge")).toHaveLength(0);
    expect(onRecorded).toHaveBeenCalledTimes(2);
    expect(onRecorded.mock.calls[0][1]).toBeUndefined();
    expect(screen.queryByTestId("liveness-steps")).not.toBeInTheDocument();
  });

  it("records without liveness when the challenge fails and it is optional", async () => {
    setup(ON, (url) => (url.endsWith("/liveness/challenge") ? jsonResponse({ detail: "down" }, 500) : undefined));
    const onRecorded = vi.fn();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<VideoRecord liveness={ON} onRecorded={onRecorded} />);
    await recordClip(user);
    expect(onRecorded).toHaveBeenCalledTimes(1);
    expect(onRecorded.mock.calls[0][1]).toBeUndefined();
    expect(screen.queryByTestId("liveness-steps")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows an error and never opens the camera when the challenge fails and it is required", async () => {
    setup(REQUIRED, (url) => (url.endsWith("/liveness/challenge") ? jsonResponse({ detail: "down" }, 500) : undefined));
    const onRecorded = vi.fn();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<VideoRecord liveness={REQUIRED} onRecorded={onRecorded} />);
    await user.click(screen.getByRole("button", { name: "Quay khuôn mặt" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Không lấy được yêu cầu kiểm tra người thật, hãy thử lại (down)");
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    expect(onRecorded).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Quay khuôn mặt" })).toBeEnabled(); // can retry
  });

  it("uses a fresh challenge for every recording", async () => {
    let n = 0;
    const fn = setup(ON, (url) =>
      url.endsWith("/liveness/challenge") ? jsonResponse({ ...CHALLENGE, challenge_token: `t${++n}` }, 201) : undefined,
    );
    const onRecorded = vi.fn();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<VideoRecord liveness={ON} onRecorded={onRecorded} />);
    await recordClip(user);
    await recordClip(user);
    expect(callsTo(fn, "/liveness/challenge")).toHaveLength(2);
    expect(onRecorded.mock.calls.map((call) => call[1])).toEqual(["t1", "t2"]);
  });

  it("mirrors only the live preview and records the raw, unmirrored stream", async () => {
    setup(ON);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<VideoRecord liveness={ON} onRecorded={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Quay khuôn mặt" }));
    const live = await screen.findByLabelText("Hình ảnh camera trực tiếp");
    expect(live).toHaveStyle({ transform: "scaleX(-1)" });
    expect(recorders).toEqual([stream]); // MediaRecorder got getUserMedia's stream itself, not a canvas/mirrored copy
    await elapse(RECORD_MS);
    expect(screen.getByLabelText("Xem lại bản quay đã ghi")).not.toHaveStyle({ transform: "scaleX(-1)" });
  });

  it("ignores a challenge that arrives after unmounting", async () => {
    let release: (response: Response) => void = () => undefined;
    const slow = new Promise<Response>((resolve) => (release = resolve));
    setup(ON, (url) => (url.endsWith("/liveness/challenge") ? (slow as unknown as Response) : undefined));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const view = render(<VideoRecord liveness={ON} onRecorded={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Quay khuôn mặt" }));
    expect(screen.getByRole("button", { name: /Quay khuôn mặt/ })).toBeDisabled(); // preparing
    view.unmount();
    release(jsonResponse(CHALLENGE, 201));
    await elapse(100);
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  });

  it("ignores a failing challenge that arrives after unmounting", async () => {
    let release: (response: Response) => void = () => undefined;
    const slow = new Promise<Response>((resolve) => (release = resolve));
    setup(REQUIRED, (url) => (url.endsWith("/liveness/challenge") ? (slow as unknown as Response) : undefined));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const view = render(<VideoRecord liveness={REQUIRED} onRecorded={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Quay khuôn mặt" }));
    view.unmount();
    release(jsonResponse({ detail: "down" }, 500));
    await elapse(100);
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  });

  it("does not start the camera if an optional challenge fails after unmounting", async () => {
    let release: (response: Response) => void = () => undefined;
    const slow = new Promise<Response>((resolve) => (release = resolve));
    setup(ON, (url) => (url.endsWith("/liveness/challenge") ? (slow as unknown as Response) : undefined));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const view = render(<VideoRecord liveness={ON} onRecorded={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Quay khuôn mặt" }));
    view.unmount();
    release(jsonResponse({ detail: "down" }, 500));
    await elapse(100);
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  });
});

describe("liveness token in the forms", () => {
  it("sign-in with the webcam sends liveness_token with the video", async () => {
    const fn = setup(ON);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await user.click(await screen.findByRole("tab", { name: "Webcam (khuôn mặt)" }));
    await recordClip(user);
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    const form = formOf(fn, "/login/webcam");
    expect(form.get("liveness_token")).toBe("lv-token");
    expect(form.get("video")).toBeInstanceOf(Blob);
    expect(callsTo(fn, "/liveness/challenge")).toHaveLength(1);
  });

  it("sign-in sends no liveness_token when liveness is off", async () => {
    const fn = setup(OFF);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await user.click(await screen.findByRole("tab", { name: "Webcam (khuôn mặt)" }));
    await recordClip(user);
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
    await waitFor(() => expect(goTo).toHaveBeenCalled());
    expect(formOf(fn, "/login/webcam").has("liveness_token")).toBe(false);
  });

  it("registration sends liveness_token with the webcam video", async () => {
    const fn = setup(ON);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await user.click(await screen.findByRole("button", { name: "Chưa có tài khoản? Đăng ký" }));
    await user.click(screen.getByRole("checkbox", { name: "Webcam (khuôn mặt)" }));
    await user.click(screen.getByRole("checkbox", { name: "Mật khẩu" }));
    await recordClip(user);
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    await waitFor(() => expect(goTo).toHaveBeenCalled());
    const form = formOf(fn, "/register/combined");
    expect(form.get("liveness_token")).toBe("lv-token");
    expect(form.get("webcam_video")).toBeInstanceOf(Blob);
  });

  it("unchecking the webcam in registration drops the recorded clip and its token", async () => {
    const fn = setup(ON);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await user.click(await screen.findByRole("button", { name: "Chưa có tài khoản? Đăng ký" }));
    await user.click(screen.getByRole("checkbox", { name: "Webcam (khuôn mặt)" }));
    await recordClip(user);
    await user.click(screen.getByRole("checkbox", { name: "Webcam (khuôn mặt)" }));
    await user.type(screen.getByLabelText(/Tên đăng nhập/), "ann");
    await user.type(screen.getByLabelText("Mật khẩu", { selector: "input[type=password]" }), "Pass-word-123X");
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    await waitFor(() => expect(goTo).toHaveBeenCalled());
    expect(formOf(fn, "/register/combined").has("liveness_token")).toBe(false);
  });

  it("the second-factor biometric step sends liveness_token with the video", async () => {
    const fn = setup(ON);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<LoginFlow />);
    await user.type(await screen.findByLabelText("Tên đăng nhập"), "ann");
    await user.type(screen.getByLabelText("Mật khẩu", { selector: "input" }), "password123");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
    await screen.findByRole("heading", { name: "Xác minh danh tính" });
    await recordClip(user, /^Quay khuôn mặt \+ giọng nói$/);
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    await waitFor(() => expect(goTo).toHaveBeenCalled());
    const form = formOf(fn, "/login/biometric");
    expect(form.get("liveness_token")).toBe("lv-token");
    expect(form.get("mfa_token")).toBe("mt");
  });

  it("the magic-link MFA step reads the config itself and applies liveness", async () => {
    const fn = setup(ON);
    window.history.replaceState({}, "", "/login/magic#token=abc");
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<MagicLoginView />);
    await user.click(await screen.findByRole("button", { name: "Đăng nhập" }));
    await screen.findByRole("heading", { name: "Xác minh danh tính" });
    await waitFor(() => expect(callsTo(fn, "/auth/config")).toHaveLength(1));
    await recordClip(user, /^Quay khuôn mặt \+ giọng nói$/);
    await user.click(screen.getByRole("button", { name: "Xác minh và đăng nhập" }));
    await waitFor(() => expect(goTo).toHaveBeenCalled());
    expect(formOf(fn, "/login/biometric").get("liveness_token")).toBe("lv-token");
  });

  it("the magic-link MFA step still works when the config cannot be read", async () => {
    setup(ON, (url) => (url.endsWith("/auth/config") ? jsonResponse({ detail: "x" }, 500) : undefined));
    window.history.replaceState({}, "", "/login/magic#token=abc");
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<MagicLoginView />);
    await user.click(await screen.findByRole("button", { name: "Đăng nhập" }));
    await screen.findByRole("heading", { name: "Xác minh danh tính" });
    expect(screen.getByRole("button", { name: /Quay khuôn mặt/ })).toBeInTheDocument();
  });

  it("linking the webcam in the account sends liveness_token (and the password)", async () => {
    const fn = setup(ON);
    const onDone = vi.fn();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<BiometricMethod kind="webcam" enabled={false} hasPassword liveness={ON} onDone={onDone} />);
    await recordClip(user);
    await user.type(screen.getByLabelText("Nhập lại mật khẩu để xác nhận"), "Pw123456!");
    await user.click(screen.getByRole("button", { name: "Lưu webcam" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const form = formOf(fn, "/me/webcam");
    expect(form.get("liveness_token")).toBe("lv-token");
    expect(form.get("password")).toBe("Pw123456!");
  });

  it("linking the webcam without liveness sends no token", async () => {
    const fn = setup(OFF);
    const onDone = vi.fn();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<BiometricMethod kind="webcam" enabled hasPassword={false} onDone={onDone} />);
    await recordClip(user);
    await user.click(screen.getByRole("button", { name: "Thay webcam" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(formOf(fn, "/me/webcam").has("liveness_token")).toBe(false);
  });
});
