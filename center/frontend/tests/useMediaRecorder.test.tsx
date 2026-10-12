import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EMPTY_RECORDING_HELP, RECORD_MS, useMediaRecorder } from "../app/hooks/useMediaRecorder";

class FakeRecorder {
  static last: FakeRecorder;
  static mime = "audio/webm";
  static data = "audio";
  state: "inactive" | "recording" = "inactive";
  get mimeType() {
    return FakeRecorder.mime;
  }
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public stream: MediaStream) {
    FakeRecorder.last = this;
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(FakeRecorder.data ? [FakeRecorder.data] : []) });
    this.onstop?.();
  }
}

const track = () => ({ stop: vi.fn() });

describe("useMediaRecorder", () => {
  let tracks: ReturnType<typeof track>[];
  let created: string[];
  let revoked: string[];

  beforeEach(() => {
    vi.useFakeTimers();
    FakeRecorder.mime = "audio/webm";
    FakeRecorder.data = "audio";
    tracks = [track()];
    created = [];
    revoked = [];
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => tracks }) },
    });
    URL.createObjectURL = vi.fn(() => {
      const url = `blob:${created.length}`;
      created.push(url);
      return url;
    });
    URL.revokeObjectURL = vi.fn((url: string) => void revoked.push(url));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  const setup = (onRecorded = vi.fn()) => ({
    onRecorded,
    ...renderHook(() => useMediaRecorder({ constraints: { audio: true }, onRecorded })),
  });

  it("records for the configured time, releases the device and returns a blob", async () => {
    const { result, onRecorded } = setup();
    await act(async () => result.current.start());
    expect(result.current.isRecording).toBe(true);
    await act(async () => void vi.advanceTimersByTime(RECORD_MS));
    expect(result.current.isRecording).toBe(false);
    expect(tracks[0].stop).toHaveBeenCalled();
    expect(onRecorded).toHaveBeenCalledWith(expect.any(Blob));
    expect(result.current.previewUrl).toBe("blob:0");
  });

  it("turns the camera off and stays silent when unmounted mid-recording", async () => {
    const { result, onRecorded, unmount } = setup();
    await act(async () => result.current.start());
    unmount();
    expect(tracks[0].stop).toHaveBeenCalled();
    expect(FakeRecorder.last.state).toBe("inactive");
    await act(async () => void vi.advanceTimersByTime(RECORD_MS * 2));
    expect(onRecorded).not.toHaveBeenCalled();
  });

  it("reports a device error without leaving anything running", async () => {
    (navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("denied"));
    const { result, onRecorded } = setup();
    await act(async () => result.current.start());
    expect(result.current.error).toContain("denied");
    expect(result.current.isRecording).toBe(false);
    expect(onRecorded).not.toHaveBeenCalled();
  });

  it("reports a non-Error device failure generically", async () => {
    (navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>).mockRejectedValue("nope");
    const { result } = setup();
    await act(async () => result.current.start());
    expect(result.current.error).toBe("Không truy cập được thiết bị");
  });

  it("releases the stream if creating the recorder fails", async () => {
    vi.stubGlobal(
      "MediaRecorder",
      class {
        constructor() {
          throw new Error("unsupported");
        }
      },
    );
    const { result } = setup();
    await act(async () => result.current.start());
    expect(tracks[0].stop).toHaveBeenCalled();
    expect(result.current.error).toContain("unsupported");
  });

  it("revokes the previous preview URL on a new recording and on unmount", async () => {
    const { result, unmount } = setup();
    await act(async () => result.current.start());
    await act(async () => void vi.advanceTimersByTime(RECORD_MS));
    await act(async () => result.current.start());
    expect(revoked).toContain("blob:0");
    await act(async () => void vi.advanceTimersByTime(RECORD_MS));
    unmount();
    expect(revoked).toContain("blob:1");
  });

  it("ignores a second start() while one is already running", async () => {
    const { result } = setup();
    await act(async () => {
      await Promise.all([result.current.start(), result.current.start()]);
    });
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(1);
  });

  it("stops the camera if the component unmounts while permission is pending", async () => {
    let grant: (s: unknown) => void = () => undefined;
    (navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise((resolve) => (grant = resolve)),
    );
    const { result, unmount, onRecorded } = setup();
    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = result.current.start();
    });
    unmount();
    await act(async () => {
      grant({ getTracks: () => tracks });
      await pending;
    });
    expect(tracks[0].stop).toHaveBeenCalled();
    expect(onRecorded).not.toHaveBeenCalled();
  });

  it("falls back to the given MIME type when the recorder reports none", async () => {
    FakeRecorder.mime = "";
    const onRecorded = vi.fn();
    const { result } = renderHook(() =>
      useMediaRecorder({ constraints: { audio: true }, onRecorded, fallbackMime: "audio/webm" }),
    );
    await act(async () => result.current.start());
    await act(async () => void vi.advanceTimersByTime(RECORD_MS));
    expect((onRecorded.mock.calls[0][0] as Blob).type).toBe("audio/webm");
  });

  it("explains an empty recording", async () => {
    FakeRecorder.data = "";
    const { result, onRecorded } = setup();
    await act(async () => result.current.start());
    await act(async () => void vi.advanceTimersByTime(RECORD_MS));
    expect(result.current.error).toBe(EMPTY_RECORDING_HELP);
    expect(onRecorded).not.toHaveBeenCalled();
  });

  it("reports recorder errors and releases the device", async () => {
    const { result } = setup();
    await act(async () => result.current.start());
    act(() => FakeRecorder.last.onerror?.());
    expect(result.current.error).toContain("gián đoạn");
    expect(result.current.isRecording).toBe(false);
    expect(tracks[0].stop).toHaveBeenCalled();
  });

  it("can record again after a recording finished", async () => {
    const { result } = setup();
    await act(async () => result.current.start());
    await act(async () => void vi.advanceTimersByTime(RECORD_MS));
    await act(async () => result.current.start());
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(2);
  });
});
