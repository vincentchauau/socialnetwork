import { ApiError, apiFetch } from "@sn/api";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { labApi } from "../app/lib/api";
import { apiErrorMessage } from "../app/lib/errors";

vi.mock("@sn/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@sn/api")>()),
  apiFetch: vi.fn().mockResolvedValue(undefined),
}));

describe("apiErrorMessage", () => {
  it.each([
    [401, "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại."],
    [403, "Yêu cầu bị từ chối (nguồn truy cập không hợp lệ)."],
    [422, "Dữ liệu không hợp lệ. Hãy kiểm tra lại các ô nhập."],
    [429, "Bạn thao tác quá nhanh. Hãy đợi một lát rồi thử lại."],
    [503, "Kafka chưa sẵn sàng"],
    [500, "Máy chủ đang gặp sự cố. Hãy thử lại sau."],
    [404, "Không kết nối được máy chủ. Hãy thử lại."],
  ])("maps %i", (status, text) => {
    expect(apiErrorMessage(new ApiError(status, "Kafka chưa sẵn sàng"))).toBe(text);
  });

  it("falls back for network errors", () => {
    expect(apiErrorMessage(new TypeError("fetch failed"))).toBe("Không kết nối được máy chủ. Hãy thử lại.");
  });
});

describe("labApi", () => {
  beforeEach(() => vi.mocked(apiFetch).mockClear());

  it("builds the expected requests", async () => {
    await labApi.status();
    await labApi.lookup("a/b");
    await labApi.clearCache("7");
    await labApi.notify("t", "b");
    await labApi.notifications();
    await labApi.log("warn", "m");
    await labApi.logs();
    await labApi.replay();
    await labApi.clearEvents();
    const calls = vi.mocked(apiFetch).mock.calls.map(([p, i]) => `${i?.method ?? "GET"} ${p}`);
    expect(calls).toEqual([
      "GET /api/lab/status",
      "GET /api/lab/users/a%2Fb",
      "DELETE /api/lab/users/7/cache",
      "POST /api/lab/notifications",
      "GET /api/lab/notifications?limit=20",
      "POST /api/lab/logs",
      "GET /api/lab/logs?limit=50",
      "GET /api/lab/logs/replay?limit=50",
      "DELETE /api/lab/events",
    ]);
    expect(vi.mocked(apiFetch).mock.calls[3][1]?.body).toBe(JSON.stringify({ title: "t", body: "b" }));
  });
});
