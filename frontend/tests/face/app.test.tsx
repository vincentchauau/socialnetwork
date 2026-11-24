import { ApiError, apiFetch, loadSession } from "@sn/api";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import FaceApp from "../../app/face/components/FaceApp";
import { CONFIRM_CLEAR, formatTime } from "../../app/face/components/History";
import { liveSummary } from "../../app/face/components/ScorePanel";
import { MISS_TOLERANCE } from "../../app/face/hooks/useFaceTracker";
import FacePage from "../_pages/face";
import { computeScores } from "../../app/face/lib/geometry";
import { averageScores } from "../../app/face/lib/smoothing";
import { H, W, buildFace } from "./helpers";
import { ctx, installBrowserStubs, makeDeps, mockBackend, pump, saved } from "./harness";

vi.mock("@sn/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@sn/api")>()),
  apiFetch: vi.fn(),
  loadSession: vi.fn(),
}));

const named = (name: string) => Object.assign(new Error(name), { name });
const startCamera = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(screen.getByRole("button", { name: "Bật camera" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Tắt camera" })).toBeInTheDocument());
};

beforeEach(() => {
  installBrowserStubs();
  mockBackend();
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("camera lifecycle", () => {
  it("starts, shows scores and disables saving until a face is tracked", async () => {
    const user = userEvent.setup();
    const { deps } = makeDeps([null, buildFace()]);
    render(<FaceApp deps={deps} />);
    const save = screen.getByRole("button", { name: "Lưu kết quả" });
    expect(save).toBeDisabled();
    expect(screen.getByText("Camera đang tắt.")).toBeInTheDocument();

    await startCamera(user);
    expect(save).toBeDisabled(); // first frame: no face yet
    await pump();
    expect(save).toBeEnabled();
    const expected = computeScores(buildFace(), W, H)!;
    expect(screen.getByText("Đối xứng").nextSibling).toHaveTextContent(`${expected.symmetry}%`);
    expect(screen.getByText("Vị trí").nextSibling).toHaveTextContent("Bạn ngồi thẳng");
  });

  it("stop() releases every track and the model, and clears the scores", async () => {
    const user = userEvent.setup();
    const { deps, stop, landmarker } = makeDeps();
    render(<FaceApp deps={deps} />);
    await startCamera(user);
    await pump();
    await user.click(screen.getByRole("button", { name: "Tắt camera" }));
    expect(stop).toHaveBeenCalledTimes(2);
    expect(landmarker.close).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Bật camera" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Lưu kết quả" })).toBeDisabled();
    expect(screen.getByText("Chưa thấy khuôn mặt", { selector: "dd" })).toBeInTheDocument();
    expect(ctx.clearRect).toHaveBeenCalled();
  });

  it("releases the camera on unmount", async () => {
    const user = userEvent.setup();
    const { deps, stop, landmarker } = makeDeps();
    const { unmount } = render(<FaceApp deps={deps} />);
    await startCamera(user);
    unmount();
    expect(stop).toHaveBeenCalledTimes(2);
    expect(landmarker.close).toHaveBeenCalled();
  });

  it("ignores a second start while running", async () => {
    const user = userEvent.setup();
    const { deps } = makeDeps();
    render(<FaceApp deps={deps} />);
    await startCamera(user);
    expect(deps.openCamera).toHaveBeenCalledTimes(1);
  });

  it("shows a Vietnamese error when permission is denied", async () => {
    const user = userEvent.setup();
    const { deps } = makeDeps();
    deps.openCamera.mockRejectedValueOnce(named("NotAllowedError"));
    render(<FaceApp deps={deps} />);
    await user.click(screen.getByRole("button", { name: "Bật camera" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("từ chối quyền dùng camera");
    expect(screen.getByRole("button", { name: "Bật camera" })).toBeEnabled();
  });

  it("stops the camera again when the model fails to load", async () => {
    const user = userEvent.setup();
    const { deps, stop } = makeDeps();
    deps.createLandmarker.mockRejectedValueOnce(named("ModelLoadError"));
    render(<FaceApp deps={deps} />);
    await user.click(screen.getByRole("button", { name: "Bật camera" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("mô hình");
    expect(stop).toHaveBeenCalledTimes(2);
  });

  it("stops and explains when frame analysis throws", async () => {
    const user = userEvent.setup();
    const { deps, stop, landmarker } = makeDeps();
    landmarker.detect.mockRejectedValue(new Error("gpu lost"));
    render(<FaceApp deps={deps} />);
    await user.click(screen.getByRole("button", { name: "Bật camera" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Không phân tích được");
    expect(stop).toHaveBeenCalledTimes(2);
    expect(landmarker.close).toHaveBeenCalled();
  });

  it("explains a missing WebGL context instead of a generic analysis error", async () => {
    const user = userEvent.setup();
    const { deps, stop, landmarker } = makeDeps();
    landmarker.detect.mockRejectedValue(named("WebglUnavailableError"));
    render(<FaceApp deps={deps} />);
    await user.click(screen.getByRole("button", { name: "Bật camera" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("WebGL");
    expect(alert).toHaveTextContent("bên ngoài VS Code");
    expect(stop).toHaveBeenCalledTimes(2);
  });

  it("releases the stream if stop is pressed while the camera is opening", async () => {
    const user = userEvent.setup();
    const { deps, stop, stream } = makeDeps();
    let release: (s: MediaStream) => void = () => undefined;
    deps.openCamera.mockReturnValueOnce(new Promise<MediaStream>((r) => { release = r; }));
    render(<FaceApp deps={deps} />);
    await user.click(screen.getByRole("button", { name: "Bật camera" }));
    expect(screen.getByText(/Đang bật camera/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tắt camera" }));
    release(stream);
    await waitFor(() => expect(stop).toHaveBeenCalledTimes(2));
    expect(deps.createLandmarker).not.toHaveBeenCalled();
  });

  it("closes the model if stop is pressed while it is loading", async () => {
    const user = userEvent.setup();
    const { deps, stop, landmarker } = makeDeps();
    let release: (l: typeof landmarker) => void = () => undefined;
    deps.createLandmarker.mockReturnValueOnce(new Promise((r) => { release = r; }));
    render(<FaceApp deps={deps} />);
    await user.click(screen.getByRole("button", { name: "Bật camera" }));
    await waitFor(() => expect(deps.createLandmarker).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "Tắt camera" }));
    release(landmarker);
    await waitFor(() => expect(landmarker.close).toHaveBeenCalledTimes(1));
    expect(stop).toHaveBeenCalledTimes(2);
  });

  it("tolerates a rejected video.play()", async () => {
    const user = userEvent.setup();
    vi.spyOn(HTMLMediaElement.prototype, "play").mockRejectedValue(new Error("blocked"));
    const { deps } = makeDeps();
    render(<FaceApp deps={deps} />);
    await startCamera(user);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("scoring loop", () => {
  it("smooths over frames with a moving average", async () => {
    const user = userEvent.setup();
    const a = buildFace();
    const b = buildFace({ skew: 0.05 });
    const { deps } = makeDeps([a, b]);
    render(<FaceApp deps={deps} />);
    await startCamera(user); // frame 1 = a
    await pump(); // frame 2 = b
    const expected = averageScores([computeScores(a, W, H)!, computeScores(b, W, H)!])!;
    expect(screen.getByText("Mắt").nextSibling).toHaveTextContent(`${expected.eye}%`);
  });

  it("keeps the last values for a few missed frames, then clears them", async () => {
    const user = userEvent.setup();
    const { deps } = makeDeps([buildFace(), ...Array.from({ length: MISS_TOLERANCE + 2 }, () => null)]);
    render(<FaceApp deps={deps} />);
    await startCamera(user);
    const save = screen.getByRole("button", { name: "Lưu kết quả" });
    await waitFor(() => expect(save).toBeEnabled());
    await pump(MISS_TOLERANCE - 2); // misses 1..MISS_TOLERANCE-2: still tracked
    expect(save).toBeEnabled();
    await pump(2);
    expect(save).toBeDisabled();
  });

  it("draws the overlay only while 'Bật vẽ' is on", async () => {
    const user = userEvent.setup();
    const { deps } = makeDeps();
    render(<FaceApp deps={deps} />);
    await startCamera(user);
    await pump();
    expect(ctx.arc).toHaveBeenCalled();
    ctx.arc.mockClear();
    await user.click(screen.getByRole("checkbox", { name: "Bật vẽ" }));
    await pump();
    expect(ctx.arc).not.toHaveBeenCalled();
    expect(ctx.drawImage).toHaveBeenCalled();
  });

  it("announces coarse text in the live region", () => {
    expect(liveSummary(null)).toBe("Chưa thấy khuôn mặt");
    expect(liveSummary({ symmetry: 93, eye: null, nose: null, mouth: null, ear: null, angle: null })).toBe("Đối xứng khoảng 95%");
  });

  it("skips drawing without a canvas context", async () => {
    const user = userEvent.setup();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    const { deps } = makeDeps();
    render(<FaceApp deps={deps} />);
    await startCamera(user);
    await pump();
    expect(screen.getByRole("button", { name: "Lưu kết quả" })).toBeEnabled();
  });
});

describe("saving and history", () => {
  it("shows the empty state, then saves the current smoothed scores and lists them first", async () => {
    const user = userEvent.setup();
    const { deps } = makeDeps();
    mockBackend([saved({ id: 1, symmetry: 80 })]);
    render(<FaceApp deps={deps} />);
    expect(screen.getByText("Đang tải lịch sử…")).toBeInTheDocument();
    await screen.findByText("Đối xứng 80%");

    await startCamera(user);
    await pump();
    await user.click(screen.getByRole("button", { name: "Lưu kết quả" }));
    expect(await screen.findByText("Đã lưu kết quả.")).toBeInTheDocument();

    const post = vi.mocked(apiFetch).mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(post[0]).toBe("/api/face/measurements");
    const sent = JSON.parse(String(post[1]!.body));
    const expected = computeScores(buildFace(), W, H)!;
    expect(sent).toEqual(expected);
    const items = within(screen.getByRole("list")).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent(`Đối xứng ${expected.symmetry}%`);
    expect(items[1]).toHaveTextContent("Đối xứng 80%");
  });

  it("shows the empty state when there is nothing saved", async () => {
    const { deps } = makeDeps();
    render(<FaceApp deps={deps} />);
    expect(await screen.findByText(/Chưa có lần đo nào/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Xoá tất cả" })).toBeDisabled();
  });

  it("reports a failed save with a Vietnamese message and re-enables the button", async () => {
    const user = userEvent.setup();
    const { deps } = makeDeps();
    render(<FaceApp deps={deps} />);
    await screen.findByText(/Chưa có lần đo nào/);
    await startCamera(user);
    await pump();
    vi.mocked(apiFetch).mockRejectedValueOnce(new ApiError(429, "Too many"));
    await user.click(screen.getByRole("button", { name: "Lưu kết quả" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("quá nhanh");
    expect(screen.getByRole("button", { name: "Lưu kết quả" })).toBeEnabled();
    expect(screen.queryByText("Đã lưu kết quả.")).toBeNull();
  });

  it("deletes one row", async () => {
    const user = userEvent.setup();
    mockBackend([saved({ id: 1 }), saved({ id: 2, symmetry: 70 })]);
    render(<FaceApp deps={makeDeps().deps} />);
    await screen.findByText("Đối xứng 70%");
    await user.click(screen.getAllByRole("button", { name: /^Xoá lần đo/ })[1]);
    await waitFor(() => expect(screen.queryByText("Đối xứng 70%")).toBeNull());
    expect(vi.mocked(apiFetch)).toHaveBeenCalledWith("/api/face/measurements/2", { method: "DELETE" });
    expect(screen.getByText("Đối xứng 90%")).toBeInTheDocument();
  });

  it("shows an error when deleting fails and keeps the row", async () => {
    const user = userEvent.setup();
    mockBackend([saved({ id: 1 })]);
    render(<FaceApp deps={makeDeps().deps} />);
    await screen.findByText("Đối xứng 90%");
    vi.mocked(apiFetch).mockRejectedValueOnce(new ApiError(404, "nf"));
    await user.click(screen.getByRole("button", { name: /^Xoá lần đo/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy bản ghi");
    expect(screen.getByText("Đối xứng 90%")).toBeInTheDocument();
  });

  it("asks for confirmation before deleting everything", async () => {
    const user = userEvent.setup();
    mockBackend([saved({ id: 1 }), saved({ id: 2 })]);
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    render(<FaceApp deps={makeDeps().deps} />);
    await screen.findAllByText("Đối xứng 90%");
    await user.click(screen.getByRole("button", { name: "Xoá tất cả" }));
    expect(confirm).toHaveBeenCalledWith(CONFIRM_CLEAR);
    expect(screen.getAllByText("Đối xứng 90%")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "Xoá tất cả" }));
    expect(await screen.findByText(/Chưa có lần đo nào/)).toBeInTheDocument();
    expect(vi.mocked(apiFetch)).toHaveBeenCalledWith("/api/face/measurements", { method: "DELETE" });
  });

  it("shows a load error with a working retry", async () => {
    const user = userEvent.setup();
    vi.mocked(apiFetch).mockRejectedValueOnce(new ApiError(401, "no"));
    render(<FaceApp deps={makeDeps().deps} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Phiên đăng nhập đã hết hạn");
    await user.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByText(/Chưa có lần đo nào/)).toBeInTheDocument();
  });

  it("renders a sparkline and trend once there are enough rows, and handles odd data", async () => {
    mockBackend([
      saved({ id: 5, symmetry: 99, ear: 90, angle: null, createdAt: "not-a-date" }),
      saved({ id: 4, symmetry: 99 }), saved({ id: 3, symmetry: 99 }),
      saved({ id: 2, symmetry: 70 }), saved({ id: 1, symmetry: 70 }),
    ]);
    render(<FaceApp deps={makeDeps().deps} />);
    expect(await screen.findByRole("img", { name: /5 lần đo/ })).toBeInTheDocument();
    expect(screen.getByText("Đang tăng nhẹ so với các lần trước")).toBeInTheDocument();
    expect(screen.getAllByText(/not-a-date/).length).toBeGreaterThan(0);
    expect(formatTime("2026-01-02T03:04:05Z")).not.toBe("2026-01-02T03:04:05Z");
  });
});

describe("page", () => {
  it("asks anonymous visitors to log in", async () => {
    vi.mocked(loadSession).mockResolvedValue(null);
    render(<FacePage />);
    expect(await screen.findByRole("link", { name: "đăng nhập" })).toBeInTheDocument();
  });
  it("reports a failing session check", async () => {
    vi.mocked(loadSession).mockRejectedValue(new Error("down"));
    render(<FacePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Không kết nối được máy chủ");
  });
  it("shows the app, with the accuracy note, to a signed-in user", async () => {
    vi.mocked(loadSession).mockResolvedValue({ id: 1, username: "a" });
    render(<FacePage />);
    expect(await screen.findByRole("button", { name: "Bật camera" })).toBeInTheDocument();
    expect(screen.getByText(/không phải đánh giá sắc đẹp hay y tế/)).toBeInTheDocument();
  });
});
