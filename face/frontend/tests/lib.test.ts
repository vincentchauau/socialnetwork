import { ApiError, apiFetch } from "@sn/api";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { faceApi } from "../app/lib/api";
import { drawFaceOverlay, ovalCrossings } from "../app/lib/draw";
import { apiErrorMessage, cameraErrorMessage } from "../app/lib/errors";
import { toPixels } from "../app/lib/geometry";
import { averageScores, pushWindow } from "../app/lib/smoothing";
import { TREND_LABEL, sparklinePoints, trendOf } from "../app/lib/trend";
import { H, W, buildFace, fakeContext, sampleScores } from "./helpers";

vi.mock("@sn/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@sn/api")>()),
  apiFetch: vi.fn(),
}));

describe("smoothing", () => {
  it("keeps only the newest N frames without mutating the input", () => {
    const first = [sampleScores({ symmetry: 1 })];
    const next = pushWindow(first, sampleScores({ symmetry: 2 }), 2);
    const last = pushWindow(next, sampleScores({ symmetry: 3 }), 2);
    expect(first).toHaveLength(1);
    expect(last.map((s) => s.symmetry)).toEqual([2, 3]);
  });
  it("averages columns, ignoring nulls, and keeps a null column null", () => {
    const avg = averageScores([
      sampleScores({ symmetry: 90, eye: 80, ear: null, angle: 89 }),
      sampleScores({ symmetry: 95, eye: null, ear: null, angle: 90.5 }),
    ])!;
    expect(avg.symmetry).toBe(93); // 92.5 rounds half up
    expect(avg.eye).toBe(80);
    expect(avg.ear).toBeNull();
    expect(avg.angle).toBe(89.8);
  });
  it("returns null for an empty window", () => {
    expect(averageScores([])).toBeNull();
  });
});

describe("trend", () => {
  it("needs more than three values", () => {
    expect(trendOf([90, 91, 92])).toBe("none");
  });
  it("detects up, down and flat (newest first)", () => {
    expect(trendOf([95, 95, 95, 80, 80])).toBe("up");
    expect(trendOf([70, 70, 70, 90, 90])).toBe("down");
    expect(trendOf([90, 91, 90, 90, 91])).toBe("flat");
    expect(Object.keys(TREND_LABEL)).toHaveLength(4);
  });
  it("builds a left-to-right polyline, oldest first, clamped to the box", () => {
    expect(sparklinePoints([100, 0], 100, 50)).toBe("0.0,50.0 100.0,0.0");
    expect(sparklinePoints([150, -10], 100, 50)).toBe("0.0,50.0 100.0,0.0");
    expect(sparklinePoints([50], 100, 50)).toBe("");
  });
});

describe("error mapping", () => {
  it.each([
    ["NotAllowedError", "từ chối"],
    ["SecurityError", "từ chối"],
    ["NotFoundError", "Không tìm thấy camera"],
    ["NotReadableError", "đang được ứng dụng khác"],
    ["UnsupportedError", "không hỗ trợ"],
    ["ModelLoadError", "mô hình"],
    ["Whatever", "Không thể bật camera"],
  ])("maps camera error %s", (name, text) => {
    const error = new Error("x");
    error.name = name;
    expect(cameraErrorMessage(error)).toContain(text);
  });
  it("accepts DOMException-like objects and non-errors", () => {
    expect(cameraErrorMessage({ name: "NotAllowedError" })).toContain("từ chối");
    expect(cameraErrorMessage("boom")).toContain("Không thể bật camera");
  });
  it.each([
    [401, "đăng nhập"],
    [403, "từ chối"],
    [404, "Không tìm thấy"],
    [422, "không hợp lệ"],
    [429, "quá nhanh"],
    [500, "Máy chủ"],
    [418, "Không kết nối"],
  ])("maps API status %i", (status, text) => {
    expect(apiErrorMessage(new ApiError(status, "x"))).toContain(text);
  });
  it("maps network failures", () => {
    expect(apiErrorMessage(new TypeError("fetch failed"))).toContain("Không kết nối");
  });
});

describe("faceApi", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset().mockResolvedValue(undefined));

  it("posts scores as JSON", async () => {
    await faceApi.save(sampleScores());
    expect(apiFetch).toHaveBeenCalledWith("/api/face/measurements", { method: "POST", body: JSON.stringify(sampleScores()) });
  });
  it("lists with a limit", async () => {
    await faceApi.list();
    await faceApi.list(5);
    expect(apiFetch).toHaveBeenNthCalledWith(1, "/api/face/measurements?limit=50");
    expect(apiFetch).toHaveBeenNthCalledWith(2, "/api/face/measurements?limit=5");
  });
  it("deletes one and all", async () => {
    await faceApi.remove("a/b");
    await faceApi.removeAll();
    expect(apiFetch).toHaveBeenNthCalledWith(1, "/api/face/measurements/a%2Fb", { method: "DELETE" });
    expect(apiFetch).toHaveBeenNthCalledWith(2, "/api/face/measurements", { method: "DELETE" });
  });
});

describe("drawFaceOverlay", () => {
  const pixels = (opts?: Parameters<typeof buildFace>[0]) => toPixels(buildFace(opts), W, H);

  it("draws oval nodes, eyes, mouth, ears and the extended centre line", () => {
    const ctx = fakeContext();
    drawFaceOverlay(ctx, pixels());
    expect(ctx.arc).toHaveBeenCalledTimes(36);
    expect(ctx.quadraticCurveTo).toHaveBeenCalledTimes(2);
    expect(ctx.stroke.mock.calls.length).toBeGreaterThan(10);
    expect(ctx.fill).toHaveBeenCalled();
  });
  it("draws nothing without an oval", () => {
    const ctx = fakeContext();
    drawFaceOverlay(ctx, []);
    expect(ctx.beginPath).not.toHaveBeenCalled();
  });
  it("skips ears and open paths whose landmarks are missing", () => {
    const ctx = fakeContext();
    drawFaceOverlay(ctx, toPixels(buildFace({ drop: [127, 356, 168, 6, 197, 195, 5, 4, 1] }), W, H));
    expect(ctx.quadraticCurveTo).not.toHaveBeenCalled();
  });
  it("falls back to a fixed extension when the line never crosses the oval", () => {
    const ctx = fakeContext();
    const pts = pixels();
    // Nose line far outside the oval, parallel to nothing it can cross.
    pts[168] = { x: 5000, y: 0 };
    pts[1] = { x: 5000, y: 10 };
    drawFaceOverlay(ctx, pts);
    expect(ctx.lineTo).toHaveBeenCalled();
  });
  it("finds crossings on both sides of the first point", () => {
    const pts = pixels();
    const { back, forward } = ovalCrossings(pts, { x: 0.5 * W, y: 0.5 * H }, { x: 0, y: 10 });
    expect(back).toBeLessThan(0);
    expect(forward).toBeGreaterThan(1);
  });
  it("ignores oval segments with missing endpoints", () => {
    const sparse: ({ x: number; y: number } | undefined)[] = [];
    expect(ovalCrossings(sparse, { x: 0, y: 0 }, { x: 0, y: 1 })).toEqual({ back: undefined, forward: undefined });
  });
});
