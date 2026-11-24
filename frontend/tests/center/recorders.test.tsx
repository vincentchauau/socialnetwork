import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AudioRecord from "../../app/center/components/AudioRecord";
import GoogleSignInButton from "../../app/center/components/GoogleSignInButton";
import VideoRecord from "../../app/center/components/VideoRecord";
import { RECORD_MS } from "../../app/center/hooks/useMediaRecorder";

class FakeRecorder {
  state = "inactive";
  mimeType = "video/webm";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["x".repeat(2048)]) });
    this.onstop?.();
  }
}

describe("recorder components", () => {
  const stop = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    stop.mockReset();
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }) },
    });
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("records video, shows previews, reports the blob and releases the tracks", async () => {
    const onRecorded = vi.fn();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<VideoRecord onRecorded={onRecorded} />);
    await user.click(screen.getByRole("button", { name: /Quay khuôn mặt/ }));
    expect(screen.getByLabelText("Hình ảnh camera trực tiếp")).toBeInTheDocument();
    await act(async () => void vi.advanceTimersByTime(RECORD_MS));
    expect(onRecorded).toHaveBeenCalledTimes(1);
    expect(stop).toHaveBeenCalled();
    expect(screen.getByLabelText("Xem lại bản quay đã ghi")).toBeInTheDocument();
    expect(screen.getByText(/2 KB/)).toBeInTheDocument();
  });

  it("records the face only by default: camera constraint without audio", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<VideoRecord onRecorded={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Quay khuôn mặt" }));
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({ video: true, audio: false });
    expect(await screen.findByRole("button", { name: /nhìn thẳng vào camera/ })).toBeInTheDocument();
    await act(async () => void vi.advanceTimersByTime(RECORD_MS));
    expect(screen.getByRole("status")).toHaveTextContent("Đã quay xong hình");
    expect(screen.getByRole("status")).not.toHaveTextContent("tiếng");
  });

  it("records face and voice only when withAudio is set (second-factor step)", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<VideoRecord withAudio onRecorded={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /Quay khuôn mặt \+ giọng nói/ }));
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({ video: true, audio: true });
    expect(await screen.findByRole("button", { name: /nhìn camera và nói/ })).toBeInTheDocument();
    await act(async () => void vi.advanceTimersByTime(RECORD_MS));
    expect(screen.getByRole("status")).toHaveTextContent("Đã quay xong hình và tiếng");
  });

  it("records audio and offers playback", async () => {
    const onRecorded = vi.fn();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<AudioRecord onRecorded={onRecorded} />);
    await user.click(screen.getByRole("button", { name: /Ghi giọng nói/ }));
    await act(async () => void vi.advanceTimersByTime(RECORD_MS));
    expect(onRecorded).toHaveBeenCalled();
    expect(screen.getByLabelText("Nghe lại giọng nói đã ghi")).toBeInTheDocument();
  });

  it("shows a device error as an alert", async () => {
    (navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("denied"));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<AudioRecord onRecorded={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /Ghi giọng nói/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("denied");
  });
});

describe("GoogleSignInButton", () => {
  afterEach(() => {
    delete window.google;
    vi.restoreAllMocks();
  });

  it("initializes Google, renders its button and forwards the credential", async () => {
    let callback: (r: { credential?: string }) => void = () => undefined;
    const renderButton = vi.fn();
    window.google = {
      accounts: {
        id: {
          initialize: (config) => {
            callback = config.callback;
          },
          renderButton,
        },
      },
    };
    const onCredential = vi.fn();
    const onError = vi.fn();
    render(<GoogleSignInButton clientId="cid" onCredential={onCredential} onError={onError} />);
    await vi.waitFor(() => expect(renderButton).toHaveBeenCalled());
    callback({ credential: "jwt" });
    callback({});
    expect(onCredential).toHaveBeenCalledWith("jwt");
    expect(onError).toHaveBeenCalledWith(expect.stringContaining("Google"));
  });
});
