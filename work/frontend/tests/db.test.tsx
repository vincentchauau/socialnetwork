import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as sn from "@sn/api";
import AuthGate from "../app/AuthGate";
import Page from "../app/page";
import CallsPanel from "../app/components/CallsPanel";
import DatabasePanel from "../app/components/DatabasePanel";
import WorkApp from "../app/components/WorkApp";
import { fileOf, listing } from "./helpers";

vi.mock("@sn/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("@sn/api")>();
  return { ...real, apiFetch: vi.fn(), apiForm: vi.fn(), loadSession: vi.fn() };
});

const fetchMock = vi.mocked(sn.apiFetch);
const formMock = vi.mocked(sn.apiForm);
const sessionMock = vi.mocked(sn.loadSession);
const apiError = (status: number, detail?: string) =>
  new sn.ApiError(status, "x", detail ? { detail } : undefined);

const tablesBody = [{ name: "people", rows: 3 }];
const page = (n: number, total = 120) => ({ columns: ["id", "name"], rows: [[n, "<b>x</b>"], [null, true]], total, page: n, pageSize: 50 });

function route(handlers: Record<string, (url: string, init?: RequestInit) => unknown>) {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const key = Object.keys(handlers).find((k) => url.startsWith(k));
    if (!key) throw new Error(`unrouted ${url}`);
    const out = handlers[key](url, init);
    if (out instanceof Error) throw out;
    return out;
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  formMock.mockReset();
  sessionMock.mockReset();
});
afterEach(() => vi.useRealTimers());

describe("DatabasePanel", () => {
  it("shows the note, tables with counts, export links", async () => {
    route({ "/api/work/db/tables": () => [{ name: "a&b", rows: 3 }] });
    render(<DatabasePanel />);
    expect(screen.getByText("Đây là cơ sở dữ liệu SQLite riêng của bạn, tách biệt khỏi dữ liệu của nền tảng.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "a&b (3 dòng)" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Xuất CSV bảng a&b" })).toHaveAttribute("href", "/api/work/db/export?table=a%26b");
  });

  it("shows empty and error states for tables", async () => {
    route({ "/api/work/db/tables": () => [] });
    const first = render(<DatabasePanel />);
    expect(await screen.findByText(/Chưa có bảng nào/)).toBeInTheDocument();
    first.unmount();
    route({ "/api/work/db/tables": () => apiError(429) });
    render(<DatabasePanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("quá nhanh");
  });

  it("views a table with pagination and debounced search", async () => {
    const seen: string[] = [];
    route({
      "/api/work/db/tables/people": (url) => {
        seen.push(url);
        const n = Number(/page=(\d+)/.exec(url)![1]);
        return page(n);
      },
      "/api/work/db/tables": () => tablesBody,
    });
    const { container } = render(<DatabasePanel />);
    await userEvent.click(await screen.findByRole("button", { name: "people (3 dòng)" }));
    expect(await screen.findByText("Trang 1 / 3 (120 dòng)")).toBeInTheDocument();
    expect(container.querySelector("b")).toBeNull();
    expect(screen.getByText("<b>x</b>", { exact: true, selector: "td" })).toBeInTheDocument();
    expect(screen.getByText("NULL")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Trước" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Sau" }));
    expect(await screen.findByText("Trang 2 / 3 (120 dòng)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Trước" }));
    expect(await screen.findByText("Trang 1 / 3 (120 dòng)")).toBeInTheDocument();

    vi.useFakeTimers({ shouldAdvanceTime: true });
    const before = seen.length;
    const box = screen.getByLabelText("Tìm kiếm");
    fireEvent.change(box, { target: { value: "a" } });
    fireEvent.change(box, { target: { value: "a&b" } });
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(seen.length).toBe(before);
    await act(async () => {
      vi.advanceTimersByTime(400);
    });
    await waitFor(() => expect(seen.length).toBe(before + 1));
    expect(seen[seen.length - 1]).toContain("q=a%26b");
    expect(seen[seen.length - 1]).toContain("page=1");
  });

  it("shows a table load error", async () => {
    route({
      "/api/work/db/tables/people": () => apiError(404),
      "/api/work/db/tables": () => tablesBody,
    });
    render(<DatabasePanel />);
    await userEvent.click(await screen.findByRole("button", { name: "people (3 dòng)" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy");
  });

  it("runs SQL with the button and Ctrl+Enter, refreshing the table list", async () => {
    let tableCalls = 0;
    route({
      "/api/work/db/tables": () => {
        tableCalls += 1;
        return tablesBody;
      },
      "/api/work/db/query": () => ({ columns: ["n"], rows: [[1], [2]], rowCount: 2, changes: 0, truncated: false }),
    });
    render(<DatabasePanel />);
    await screen.findByText("people (3 dòng)");
    await userEvent.click(screen.getByRole("button", { name: "Chạy" }));
    expect(fetchMock).not.toHaveBeenCalledWith("/api/work/db/query", expect.anything());
    await userEvent.type(screen.getByLabelText(/Một câu lệnh SQL/), "select 1");
    await userEvent.click(screen.getByRole("button", { name: "Chạy" }));
    expect(await screen.findByText(/2 dòng, 0 thay đổi/)).toBeInTheDocument();
    expect(screen.queryByText(/đã cắt bớt/)).toBeNull();
    fireEvent.keyDown(screen.getByLabelText(/Một câu lệnh SQL/), { key: "Enter" });
    expect(fetchMock.mock.calls.filter((c) => c[0] === "/api/work/db/query")).toHaveLength(1);
    fireEvent.keyDown(screen.getByLabelText(/Một câu lệnh SQL/), { key: "Enter", ctrlKey: true });
    await waitFor(() => expect(fetchMock.mock.calls.filter((c) => c[0] === "/api/work/db/query")).toHaveLength(2));
    expect(fetchMock).toHaveBeenCalledWith("/api/work/db/query", { method: "POST", body: JSON.stringify({ sql: "select 1" }) });
    await waitFor(() => expect(tableCalls).toBeGreaterThan(2));
  });

  it("notes truncated results and shows SQL errors inline", async () => {
    let fail = false;
    route({
      "/api/work/db/tables": () => [],
      "/api/work/db/query": () =>
        fail ? apiError(400, "Lỗi cú pháp SQL") : { columns: ["n"], rows: [[1]], rowCount: 1, changes: 4, truncated: true },
    });
    render(<DatabasePanel />);
    await userEvent.type(screen.getByLabelText(/Một câu lệnh SQL/), "x");
    await userEvent.click(screen.getByRole("button", { name: "Chạy" }));
    expect(await screen.findByText(/Kết quả đã cắt bớt/)).toBeInTheDocument();
    expect(screen.getByText(/1 dòng, 4 thay đổi/)).toBeInTheDocument();
    fail = true;
    await userEvent.click(screen.getByRole("button", { name: "Chạy" }));
    expect(await screen.findByText("Lỗi cú pháp SQL")).toBeInTheDocument();
    expect(screen.queryByText(/Kết quả đã cắt bớt/)).toBeNull();
  });

  it("imports CSV with client-side checks", async () => {
    route({ "/api/work/db/tables": () => [] });
    formMock.mockResolvedValue({ table: "t1", rows: 7 });
    const { container } = render(<DatabasePanel />);
    await screen.findByText(/Chưa có bảng nào/);
    const submit = screen.getByRole("button", { name: "Nhập" });
    await userEvent.click(submit);
    expect(screen.getByRole("alert")).toHaveTextContent("Tên bảng");
    await userEvent.type(screen.getByLabelText("Tên bảng"), "t1");
    await userEvent.click(submit);
    expect(screen.getByRole("alert")).toHaveTextContent("Hãy chọn tệp CSV");
    const input = container.querySelector("#import-file") as HTMLInputElement;
    await userEvent.upload(input, fileOf("big.csv", 3 * 1024 * 1024));
    await userEvent.click(submit);
    expect(screen.getByRole("alert")).toHaveTextContent("2 MB");
    await userEvent.upload(input, fileOf("a.csv", 100));
    await userEvent.click(submit);
    expect(await screen.findByText("Đã nhập 7 dòng vào bảng t1.")).toBeInTheDocument();
    expect(formMock.mock.calls[0][0]).toBe("/api/work/db/import");
    const form = formMock.mock.calls[0][1] as FormData;
    expect(form.get("table")).toBe("t1");
    expect(form.get("file")).toBeInstanceOf(File);
  });

  it("maps import errors", async () => {
    route({ "/api/work/db/tables": () => [] });
    formMock.mockRejectedValue(apiError(413));
    const { container } = render(<DatabasePanel />);
    await screen.findByText(/Chưa có bảng nào/);
    await userEvent.type(screen.getByLabelText("Tên bảng"), "t1");
    await userEvent.upload(container.querySelector("#import-file") as HTMLInputElement, fileOf("a.csv", 10));
    await userEvent.click(screen.getByRole("button", { name: "Nhập" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("quá lớn");
  });

  it("resets the database only after confirmation", async () => {
    let fail = false;
    route({
      "/api/work/db/tables": () => tablesBody,
      "/api/work/db": (_u, init) => (fail ? apiError(429) : init?.method === "DELETE" ? undefined : null),
    });
    render(<DatabasePanel />);
    await screen.findByText("people (3 dòng)");
    await userEvent.click(screen.getByRole("button", { name: "Xoá toàn bộ cơ sở dữ liệu thử" }));
    await userEvent.click(screen.getByRole("button", { name: "Huỷ" }));
    expect(fetchMock).not.toHaveBeenCalledWith("/api/work/db", { method: "DELETE" });
    await userEvent.click(screen.getByRole("button", { name: "Xoá toàn bộ cơ sở dữ liệu thử" }));
    fail = true;
    await userEvent.click(screen.getByRole("button", { name: "Xác nhận xoá tất cả" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("quá nhanh");
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Xác nhận xoá tất cả" }));
    expect(await screen.findByText("Đã xoá toàn bộ cơ sở dữ liệu thử.")).toBeInTheDocument();
  });
});

describe("CallsPanel", () => {
  it("renders events as text, with empty and error states", async () => {
    fetchMock.mockResolvedValueOnce([{ id: 1, eventType: "<i>call</i>", fromNumber: "+84***123", toNumber: "+84***999", createdAt: "t" }]);
    const first = render(<CallsPanel />);
    expect(await screen.findByText("<i>call</i>")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/work/calls?limit=50");
    first.unmount();
    fetchMock.mockResolvedValueOnce([]);
    const second = render(<CallsPanel />);
    expect(await screen.findByText("Chưa có cuộc gọi nào.")).toBeInTheDocument();
    second.unmount();
    fetchMock.mockRejectedValueOnce(apiError(403));
    render(<CallsPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("không có quyền");
  });
});

describe("WorkApp and page", () => {
  beforeEach(() => {
    route({
      "/api/work/files": () => listing("/", []),
      "/api/work/db/tables": () => [],
      "/api/work/calls": () => [],
    });
  });

  it("hides the Cuộc gọi tab from non-admins", async () => {
    render(<WorkApp isAdmin={false} />);
    expect(screen.getByRole("tab", { name: "Tệp" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Cơ sở dữ liệu" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Cuộc gọi" })).toBeNull();
    await userEvent.click(screen.getByRole("tab", { name: "Cơ sở dữ liệu" }));
    expect(await screen.findByText(/Chưa có bảng nào/)).toBeInTheDocument();
  });

  it("shows the Cuộc gọi tab to admins", async () => {
    render(<WorkApp isAdmin />);
    await userEvent.click(screen.getByRole("tab", { name: "Cuộc gọi" }));
    expect(await screen.findByText("Chưa có cuộc gọi nào.")).toBeInTheDocument();
  });

  it("derives admin from the session role", async () => {
    sessionMock.mockResolvedValue({ id: 1, username: "a", role: "admin" } as never);
    const first = render(<Page />);
    expect(await screen.findByRole("tab", { name: "Cuộc gọi" })).toBeInTheDocument();
    first.unmount();
    sessionMock.mockResolvedValue({ id: 2, username: "b" });
    render(<Page />);
    await screen.findByRole("tab", { name: "Tệp" });
    expect(screen.queryByRole("tab", { name: "Cuộc gọi" })).toBeNull();
  });

  it("covers the AuthGate states", async () => {
    sessionMock.mockResolvedValue(null);
    const a = render(<AuthGate title="T">{() => <p>in</p>}</AuthGate>);
    expect(screen.getByText("Đang tải…")).toBeInTheDocument();
    expect(await screen.findByText("đăng nhập")).toBeInTheDocument();
    a.unmount();
    sessionMock.mockRejectedValue(new Error("down"));
    render(<AuthGate title="T">{() => <p>in</p>}</AuthGate>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Không kết nối");
  });
});
