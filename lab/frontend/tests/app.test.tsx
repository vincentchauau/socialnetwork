import { apiFetch, loadSession } from "@sn/api";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CONFIRM_CLEAR_EVENTS } from "../app/components/LabApp";
import { MESSAGING_HINT } from "../app/components/StatusBar";
import LabPage from "../app/page";
import { ALL_UP, MESSAGING_OFF, apiError, countCalls, logRow, mockRoutes, note } from "./helpers";
import type { Routes } from "./helpers";

vi.mock("@sn/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@sn/api")>()),
  apiFetch: vi.fn(),
  loadSession: vi.fn(),
}));

const XSS = "<img src=x onerror=alert(1)>";
const base = (over: Routes = {}): Routes => ({
  "GET /api/lab/status": ALL_UP,
  "GET /api/lab/notifications": [],
  "GET /api/lab/logs": [],
  ...over,
});

const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
async function open(routes: Routes = base()) {
  const calls = mockRoutes(routes);
  const user = userEvent.setup({ delay: null });
  render(<LabPage />);
  await advance(0);
  return { user, calls };
}
const type = async (user: ReturnType<typeof userEvent.setup>, label: string, text: string) => {
  const field = screen.getByLabelText(label);
  await user.clear(field);
  await user.type(field, text);
};
const click = async (user: ReturnType<typeof userEvent.setup>, name: string) => {
  await user.click(screen.getByRole("button", { name }));
  await advance(0);
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(loadSession).mockResolvedValue({ id: 1, username: "an" });
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.mocked(apiFetch).mockReset();
});

describe("auth gate", () => {
  it("asks anonymous users to sign in and does not call the lab", async () => {
    vi.mocked(loadSession).mockResolvedValue(null);
    render(<LabPage />);
    await advance(0);
    expect(screen.getByRole("link", { name: "đăng nhập" })).toBeInTheDocument();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("shows an error when the session cannot be loaded", async () => {
    vi.mocked(loadSession).mockRejectedValue(new Error("down"));
    render(<LabPage />);
    await advance(0);
    expect(screen.getByRole("alert")).toHaveTextContent("Không kết nối được máy chủ");
  });

  it("shows loading first", () => {
    vi.mocked(loadSession).mockReturnValue(new Promise(() => {}));
    render(<LabPage />);
    expect(screen.getByText("Đang tải…")).toBeInTheDocument();
  });
});

describe("status bar", () => {
  it("shows four badges with accessible state", async () => {
    await open();
    const list = screen.getByRole("list", { name: "Trạng thái dịch vụ" });
    for (const name of ["Redis", "gRPC", "RabbitMQ", "Kafka"]) {
      expect(within(list).getByText(name).closest("li")).toHaveClass("on");
    }
    expect(within(list).getAllByText(": đang chạy")).toHaveLength(4);
    expect(screen.queryByText(MESSAGING_HINT)).not.toBeInTheDocument();
  });

  it("explains how to enable messaging and disables the queue and log buttons", async () => {
    await open(base({ "GET /api/lab/status": MESSAGING_OFF }));
    expect(screen.getByText(MESSAGING_HINT)).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Trạng thái dịch vụ" });
    expect(within(list).getByText("RabbitMQ").closest("li")).not.toHaveClass("on");
    expect(within(list).getByText("Redis").closest("li")).toHaveClass("on");
    expect(within(list).getByText("RabbitMQ").nextElementSibling).toHaveTextContent(": không chạy");
    await type(userEvent.setup({ delay: null }), "Tiêu đề", "x");
    expect(screen.getByRole("button", { name: "Gửi" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Gửi nhật ký" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Phát lại từ đầu" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Tra" })).toBeEnabled();
  });

  it("polls every 5 seconds and updates", async () => {
    let status = ALL_UP;
    const { calls } = await open(base({ "GET /api/lab/status": () => status }));
    expect(countCalls(calls, "GET /api/lab/status")).toBe(1);
    status = MESSAGING_OFF;
    await advance(5000);
    expect(countCalls(calls, "GET /api/lab/status")).toBe(2);
    expect(screen.getByText(MESSAGING_HINT)).toBeInTheDocument();
  });

  it("shows the failure and keeps polling", async () => {
    const { calls } = await open(base({ "GET /api/lab/status": apiError(503, "Redis không phản hồi") }));
    expect(screen.getByText("Redis không phản hồi")).toBeInTheDocument();
    await advance(5000);
    expect(countCalls(calls, "GET /api/lab/status")).toBe(2);
  });
});

describe("lookup panel", () => {
  const user1 = { id: "1", name: "An", source: "grpc", ms: 12 };

  it("shows name, source, latency and keeps the last 5 lookups", async () => {
    let n = 0;
    const { user } = await open(
      base({
        "GET /api/lab/users/1": () => ({ ...user1, name: `An${++n}`, source: n === 1 ? "grpc" : "cache", ms: n }),
      }),
    );
    expect(screen.getByLabelText("Mã người dùng")).toHaveValue("1");
    await click(user, "Tra");
    const status = screen.getAllByRole("status")[0];
    expect(status).toHaveTextContent("An1");
    expect(status).toHaveTextContent("Từ gRPC");
    expect(status).toHaveTextContent("1 ms");
    for (let i = 0; i < 6; i++) await click(user, "Tra");
    expect(screen.getAllByRole("status")[0]).toHaveTextContent("Từ cache Redis");
    const table = screen.getByRole("table", { name: "5 lần tra gần nhất" });
    expect(within(table).getAllByRole("row")).toHaveLength(6);
    expect(within(table).getByText("An7")).toBeInTheDocument();
    expect(within(table).queryByText("An1")).not.toBeInTheDocument();
  });

  it("rejects invalid ids without calling the backend", async () => {
    const { user, calls } = await open();
    await type(user, "Mã người dùng", "a b!");
    await click(user, "Tra");
    expect(screen.getByRole("alert")).toHaveTextContent("1–16 ký tự");
    await click(user, "Xoá cache");
    expect(calls.some((c) => c.includes("/users/"))).toBe(false);
  });

  it.each([
    [503, "Dịch vụ gRPC đang tắt", "Dịch vụ gRPC đang tắt"],
    [429, "slow", "quá nhanh"],
    [422, "bad", "không hợp lệ"],
    [401, "x", "hết hạn"],
  ])("shows a Vietnamese message for %i", async (status, detail, text) => {
    const { user } = await open(base({ "GET /api/lab/users/1": apiError(status, detail) }));
    await click(user, "Tra");
    expect(screen.getByRole("alert")).toHaveTextContent(text);
    expect(screen.getByRole("button", { name: "Tra" })).toBeEnabled();
  });

  it("clears the cache", async () => {
    const { user, calls } = await open(base({ "DELETE /api/lab/users/1/cache": undefined }));
    await click(user, "Xoá cache");
    expect(countCalls(calls, "DELETE /api/lab/users/1/cache")).toBe(1);
    expect(screen.getAllByRole("status")[0]).toHaveTextContent("Đã xoá cache của người dùng 1");
  });

  it("reports a failed cache clear", async () => {
    const { user } = await open(base({ "DELETE /api/lab/users/1/cache": apiError(503, "Redis tắt") }));
    await click(user, "Xoá cache");
    expect(screen.getByRole("alert")).toHaveTextContent("Redis tắt");
  });

  it("renders user names as text", async () => {
    const { user } = await open(base({ "GET /api/lab/users/1": { ...user1, name: XSS } }));
    await click(user, "Tra");
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getAllByText(XSS).length).toBeGreaterThan(0);
  });
});

describe("queue panel", () => {
  it("counts characters, posts and refreshes the table", async () => {
    let rows = [note({ id: 1, title: "Cũ" })];
    const { user, calls } = await open(
      base({
        "GET /api/lab/notifications": () => rows,
        "POST /api/lab/notifications": (init?: RequestInit) => {
          rows = [note({ id: 2, title: "Mới", status: "queued", attempts: 0 }), ...rows];
          expect(JSON.parse(String(init?.body))).toEqual({ title: "Mới", body: "nd" });
          return { id: 2 };
        },
      }),
    );
    expect(screen.getByRole("table", { name: "Thông báo gần đây" })).toHaveTextContent("Cũ");
    await type(user, "Tiêu đề", "Mới");
    await type(user, "Nội dung thông báo", "nd");
    expect(screen.getByText("3/80")).toBeInTheDocument();
    expect(screen.getByText("2/300")).toBeInTheDocument();
    await click(user, "Gửi");
    expect(screen.getByText("Đã gửi vào hàng đợi (mã 2).")).toBeInTheDocument();
    expect(screen.getByLabelText("Tiêu đề")).toHaveValue("");
    const table = screen.getByRole("table", { name: "Thông báo gần đây" });
    expect(within(table).getByText("queued")).toBeInTheDocument();
    expect(countCalls(calls, "GET /api/lab/notifications")).toBe(2);
  });

  it("disables sending without a title and fills the failing sample", async () => {
    const { user } = await open();
    expect(screen.getByRole("button", { name: "Gửi" })).toBeDisabled();
    expect(screen.getByText(/Tiêu đề bắt đầu bằng \[fail\]/)).toBeInTheDocument();
    await click(user, "Gửi thử tin lỗi");
    expect(screen.getByLabelText("Tiêu đề")).toHaveValue("[fail] Tin thử lỗi");
    expect(screen.getByRole("button", { name: "Gửi" })).toBeEnabled();
  });

  it.each([
    [503, "RabbitMQ chưa sẵn sàng", "RabbitMQ chưa sẵn sàng"],
    [429, "x", "quá nhanh"],
    [422, "x", "không hợp lệ"],
  ])("shows a message for %i when sending", async (status, detail, text) => {
    const { user } = await open(base({ "POST /api/lab/notifications": apiError(status, detail) }));
    await type(user, "Tiêu đề", "a");
    await click(user, "Gửi");
    expect(screen.getByRole("alert")).toHaveTextContent(text);
    expect(screen.getByLabelText("Tiêu đề")).toHaveValue("a");
  });

  it("polls every 10 s when idle and every 2 s while a row is active, without overlap", async () => {
    let rows = [note({ status: "processing", attempts: 1 })];
    let release: () => void = () => {};
    let slow = false;
    const { calls } = await open(
      base({
        "GET /api/lab/notifications": () =>
          slow ? new Promise<void>((r) => { release = r; }).then(() => rows) : rows,
      }),
    );
    expect(countCalls(calls, "GET /api/lab/notifications")).toBe(1);
    await advance(2000);
    expect(countCalls(calls, "GET /api/lab/notifications")).toBe(2);
    await advance(2000);
    expect(countCalls(calls, "GET /api/lab/notifications")).toBe(3);

    rows = [note({ status: "done" })];
    await advance(2000);
    expect(countCalls(calls, "GET /api/lab/notifications")).toBe(4);
    await advance(9000);
    expect(countCalls(calls, "GET /api/lab/notifications")).toBe(4);
    await advance(1000);
    expect(countCalls(calls, "GET /api/lab/notifications")).toBe(5);

    slow = true;
    await advance(10_000);
    expect(countCalls(calls, "GET /api/lab/notifications")).toBe(6);
    await advance(60_000);
    expect(countCalls(calls, "GET /api/lab/notifications")).toBe(6);
    slow = false;
    await act(async () => release());
  });

  it("shows chips for every state, attempts, and plain-text titles", async () => {
    await open(
      base({
        "GET /api/lab/notifications": [
          note({ id: 1, status: "queued", attempts: 0 }),
          note({ id: 2, status: "retrying", attempts: 2 }),
          note({ id: 3, status: "dead", attempts: 3, title: XSS }),
          note({ id: 4, status: "done" }),
        ],
      }),
    );
    const table = screen.getByRole("table", { name: "Thông báo gần đây" });
    for (const s of ["queued", "retrying", "dead", "done"]) expect(within(table).getByText(s)).toBeInTheDocument();
    expect(within(table).getByText(XSS)).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(within(table).getByText("dead")).toHaveClass("dead");
  });

  it("reports a failed list refresh and recovers", async () => {
    let fail = true;
    await open(base({ "GET /api/lab/notifications": () => (fail ? apiError(503, "Hàng đợi tắt") : []) }));
    expect(screen.getByText("Hàng đợi tắt")).toBeInTheDocument();
    fail = false;
    await advance(10_000);
    expect(screen.queryByText("Hàng đợi tắt")).not.toBeInTheDocument();
  });
});

describe("logs panel", () => {
  it("posts a log with its level and refreshes", async () => {
    let rows = [logRow({ message: "cũ" })];
    const { user } = await open(
      base({
        "GET /api/lab/logs": () => rows,
        "POST /api/lab/logs": (init?: RequestInit) => {
          const body = JSON.parse(String(init?.body));
          rows = [logRow({ level: body.level, message: body.message, offset: 1 }), ...rows];
          return undefined;
        },
      }),
    );
    expect(screen.getByRole("table", { name: "Nhật ký mới nhất" })).toHaveTextContent("cũ");
    await user.selectOptions(screen.getByLabelText("Mức"), "error");
    await type(user, "Nội dung nhật ký", "hỏng");
    expect(screen.getAllByText(/\/200$/)[0]).toHaveTextContent("4/200");
    await click(user, "Gửi nhật ký");
    expect(screen.getByText("Đã gửi nhật ký vào Kafka.")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Nhật ký mới nhất" });
    expect(within(table).getByText("hỏng")).toBeInTheDocument();
    expect(within(table).getByText("error")).toHaveClass("error");
    expect(within(table).getByText("0 / 1")).toBeInTheDocument();
  });

  it("polls every 3 seconds", async () => {
    const { calls } = await open();
    await advance(3000);
    await advance(3000);
    expect(countCalls(calls, "GET /api/lab/logs")).toBe(3);
  });

  it.each([
    [503, "Kafka chưa sẵn sàng", "Kafka chưa sẵn sàng"],
    [429, "x", "quá nhanh"],
    [422, "x", "không hợp lệ"],
  ])("shows a message for %i when sending", async (status, detail, text) => {
    const { user } = await open(base({ "POST /api/lab/logs": apiError(status, detail) }));
    await type(user, "Nội dung nhật ký", "a");
    await click(user, "Gửi nhật ký");
    expect(screen.getByRole("alert")).toHaveTextContent(text);
  });

  it("replays the topic in a separate list", async () => {
    const { user } = await open(
      base({
        "GET /api/lab/logs/replay": { fromBeginning: true, messages: [logRow({ message: "đầu tiên" }), logRow({ level: "warn", message: XSS, partition: 1, offset: 4 })] },
      }),
    );
    expect(screen.queryByText("Đọc lại từ đầu chủ đề (replay)")).not.toBeInTheDocument();
    await click(user, "Phát lại từ đầu");
    const region = screen.getByRole("region", { name: "Đọc lại từ đầu chủ đề (replay)" });
    expect(within(region).getByText(/Kafka giữ tin theo thời hạn/)).toBeInTheDocument();
    const items = within(region).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("[info] đầu tiên (0/0)");
    expect(items[1]).toHaveTextContent(`[warn] ${XSS} (1/4)`);
    expect(document.querySelector("img")).toBeNull();
  });

  it("says when the topic is empty and when replay fails", async () => {
    const routes = base({ "GET /api/lab/logs/replay": { fromBeginning: true, messages: [] } });
    const { user } = await open(routes);
    await click(user, "Phát lại từ đầu");
    expect(screen.getByText("Chủ đề chưa có tin nào.")).toBeInTheDocument();
  });

  it("shows replay errors", async () => {
    const { user } = await open(base({ "GET /api/lab/logs/replay": apiError(503, "Kafka tắt") }));
    await click(user, "Phát lại từ đầu");
    expect(screen.getByRole("alert")).toHaveTextContent("Kafka tắt");
  });

  it("shows list errors", async () => {
    await open(base({ "GET /api/lab/logs": apiError(429, "x") }));
    expect(screen.getByRole("alert")).toHaveTextContent("quá nhanh");
  });
});

describe("guide and cleanup", () => {
  it("has a collapsible guide", async () => {
    await open();
    const guide = screen.getByText("Khi nào dùng cái nào?").closest("details")!;
    expect(guide).not.toHaveAttribute("open");
    expect(guide).toHaveTextContent("giao việc làm một lần");
    expect(guide).toHaveTextContent("lưu sự kiện, nhiều bên cùng đọc");
    expect(guide).toHaveTextContent("hỏi đáp tức thì");
  });

  it("deletes after confirmation", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { user, calls } = await open(base({ "DELETE /api/lab/events": undefined }));
    await click(user, "Xoá dữ liệu thử của tôi");
    expect(confirm).toHaveBeenCalledWith(CONFIRM_CLEAR_EVENTS);
    expect(countCalls(calls, "DELETE /api/lab/events")).toBe(1);
    expect(screen.getByText("Đã xoá dữ liệu thử của bạn.")).toBeInTheDocument();
  });

  it("does nothing when the confirmation is declined", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { user, calls } = await open();
    await click(user, "Xoá dữ liệu thử của tôi");
    expect(countCalls(calls, "DELETE /api/lab/events")).toBe(0);
  });

  it("shows an error when deleting fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { user } = await open(base({ "DELETE /api/lab/events": apiError(503, "Kafka tắt") }));
    await click(user, "Xoá dữ liệu thử của tôi");
    expect(screen.getByRole("alert")).toHaveTextContent("Kafka tắt");
  });
});

describe("whole page", () => {
  it("stops all polling on unmount", async () => {
    const calls = mockRoutes(base());
    const { unmount } = render(<LabPage />);
    await advance(0);
    await advance(10_000);
    const before = calls.length;
    unmount();
    await advance(60_000);
    expect(calls.length).toBe(before);
  });
});
