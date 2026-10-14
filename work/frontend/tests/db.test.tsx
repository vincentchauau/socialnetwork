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
import { tableNameFromFile } from "../app/components/DatabasePanel";

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
  it("shows the note and the tables in the selector, and exports the selected one", async () => {
    route({
      "/api/work/db/tables/a%26b": () => page(1),
      "/api/work/db/tables": () => [{ name: "a&b", rows: 3 }],
    });
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    render(<DatabasePanel />);
    expect(screen.getByText(/Đây là cơ sở dữ liệu SQLite riêng của bạn/)).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: "a&b (3 dòng)" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Export" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    expect(assign).toHaveBeenCalledWith("/api/work/db/export?table=a%26b");
    vi.unstubAllGlobals();
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

  it("shows the table as a rows x columns tile grid, with the original paging buttons and debounced search", async () => {
    const seen: string[] = [];
    route({
      "/api/work/db/tables/people": (url) => {
        seen.push(url);
        const n = Number(/page=(\d+)/.exec(url)![1]);
        return { ...page(n), pageSize: 6 };
      },
      "/api/work/db/tables": () => tablesBody,
    });
    const { container } = render(<DatabasePanel />);
    expect(await screen.findByText(/Trang 1 \/ 20 \(120 dòng\)/)).toBeInTheDocument();
    expect(seen[0]).toContain("pageSize=6"); // 3 rows x 2 columns
    expect(container.querySelector("b")?.textContent).toBe("id"); // header row, not user markup
    expect(screen.getByText("<b>x</b>")).toBeInTheDocument();
    expect(screen.getByText("NULL")).toBeInTheDocument();
    const grid = container.querySelector(".maxGridContainer") as HTMLElement;
    expect(grid.style.gridTemplateColumns).toBe("repeat(2, 1fr)");
    expect(grid.querySelectorAll(".grid-item")).toHaveLength(2);

    expect(screen.getByRole("button", { name: "First" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "+10" }));
    expect(await screen.findByRole("button", { name: "Page 11" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "-1" }));
    expect(await screen.findByRole("button", { name: "Page 10" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Last" }));
    expect(await screen.findByRole("button", { name: "Page 20" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "+1" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "First" }));
    expect(await screen.findByRole("button", { name: "Page 1" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Số cột"), { target: { value: "4" } });
    await waitFor(() => expect(seen[seen.length - 1]).toContain("pageSize=12"));
    expect((container.querySelector(".maxGridContainer") as HTMLElement).style.gridTemplateColumns).toBe("repeat(4, 1fr)");

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
    vi.useRealTimers();
    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(box).toHaveValue("");
    await userEvent.type(box, "z");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(seen[seen.length - 1]).toContain("q=z"));
  });

  it("shows a table load error", async () => {
    route({
      "/api/work/db/tables/people": () => apiError(404),
      "/api/work/db/tables": () => tablesBody,
    });
    render(<DatabasePanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy");
  });

  it("runs SQL from the SQL button with Run and Ctrl+Enter, refreshing the table list", async () => {
    let tableCalls = 0;
    route({
      "/api/work/db/tables/people": () => page(1),
      "/api/work/db/tables": () => {
        tableCalls += 1;
        return tablesBody;
      },
      "/api/work/db/query": () => ({ columns: ["n"], rows: [[1], [2]], rowCount: 2, changes: 0, truncated: false }),
    });
    render(<DatabasePanel />);
    await screen.findByRole("option", { name: "people (3 dòng)" });
    expect(screen.queryByLabelText(/Một câu lệnh SQL/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "SQL" }));
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
    await userEvent.click(screen.getByRole("button", { name: "SQL" }));
    expect(screen.queryByLabelText(/Một câu lệnh SQL/)).toBeNull();
  });

  it("notes truncated results and shows SQL errors inline", async () => {
    let fail = false;
    route({
      "/api/work/db/tables": () => [],
      "/api/work/db/query": () =>
        fail ? apiError(400, "Lỗi cú pháp SQL") : { columns: ["n"], rows: [[1]], rowCount: 1, changes: 4, truncated: true },
    });
    render(<DatabasePanel />);
    await userEvent.click(screen.getByRole("button", { name: "SQL" }));
    await userEvent.type(screen.getByLabelText(/Một câu lệnh SQL/), "x");
    await userEvent.click(screen.getByRole("button", { name: "Chạy" }));
    expect(await screen.findByText(/Kết quả đã cắt bớt/)).toBeInTheDocument();
    expect(screen.getByText(/1 dòng, 4 thay đổi/)).toBeInTheDocument();
    fail = true;
    await userEvent.click(screen.getByRole("button", { name: "Chạy" }));
    expect(await screen.findByText("Lỗi cú pháp SQL")).toBeInTheDocument();
    expect(screen.queryByText(/Kết quả đã cắt bớt/)).toBeNull();
  });

  it("imports a CSV with client-side checks, naming the table after the file", async () => {
    route({ "/api/work/db/tables": () => [] });
    formMock.mockResolvedValue({ table: "my_data", rows: 7 });
    render(<DatabasePanel />);
    await screen.findByText(/Chưa có bảng nào/);
    const input = screen.getByLabelText("Tệp CSV") as HTMLInputElement;
    await userEvent.upload(input, fileOf("!!!.csv", 100));
    expect(screen.getByRole("alert")).toHaveTextContent("Tên tệp");
    await userEvent.upload(input, fileOf("big.csv", 3 * 1024 * 1024));
    expect(screen.getByRole("alert")).toHaveTextContent("2 MB");
    await userEvent.upload(input, fileOf("my data.csv", 100));
    expect(await screen.findByText("Đã nhập 7 dòng vào bảng my_data.")).toBeInTheDocument();
    expect(formMock.mock.calls[0][0]).toBe("/api/work/db/import");
    const form = formMock.mock.calls[0][1] as FormData;
    expect(form.get("table")).toBe("my_data");
    expect(form.get("file")).toBeInstanceOf(File);
  });

  it("opens the file chooser from Import and maps import errors", async () => {
    route({ "/api/work/db/tables": () => [] });
    formMock.mockRejectedValue(apiError(413));
    render(<DatabasePanel />);
    await screen.findByText(/Chưa có bảng nào/);
    const click = vi.spyOn(HTMLInputElement.prototype, "click");
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(click).toHaveBeenCalled();
    click.mockRestore();
    await userEvent.upload(screen.getByLabelText("Tệp CSV"), fileOf("a.csv", 10));
    expect(await screen.findByRole("alert")).toHaveTextContent("quá lớn");
    fireEvent.change(screen.getByLabelText("Tệp CSV"), { target: { files: [] } }); // cancelled chooser: nothing happens
  });

  it("derives table names from file names", () => {
    expect(tableNameFromFile("my data.csv")).toBe("my_data");
    expect(tableNameFromFile("2024.csv")).toBe("t_2024");
    expect(tableNameFromFile("..csv")).toBe("");
  });

  it("resets the database only after confirmation", async () => {
    let fail = false;
    route({
      "/api/work/db/tables/people": () => page(1),
      "/api/work/db/tables": () => tablesBody,
      "/api/work/db": (_u, init) => (fail ? apiError(429) : init?.method === "DELETE" ? undefined : null),
    });
    render(<DatabasePanel />);
    await screen.findByRole("option", { name: "people (3 dòng)" });
    await userEvent.click(screen.getByRole("button", { name: "Reset" }));
    await userEvent.click(screen.getByRole("button", { name: "Huỷ" }));
    expect(fetchMock).not.toHaveBeenCalledWith("/api/work/db", { method: "DELETE" });
    await userEvent.click(screen.getByRole("button", { name: "Reset" }));
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

  it("hides Calls from non-admins and switches views with File and Database", async () => {
    render(<WorkApp username="alice" isAdmin={false} />);
    expect(screen.getByRole("button", { name: "File" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Database" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Calls" })).toBeNull();
    expect(await screen.findByText("Thư mục này đang trống.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Database" }));
    expect(await screen.findByText(/Chưa có bảng nào/)).toBeInTheDocument();
    expect(window.location.hash).toBe("#database");
    expect(screen.getByRole("button", { name: "Database" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows Calls to admins", async () => {
    render(<WorkApp username="root" isAdmin />);
    await userEvent.click(screen.getByRole("button", { name: "Calls" }));
    expect(await screen.findByText("Chưa có cuộc gọi nào.")).toBeInTheDocument();
  });

  it("opens the view named in the URL hash, but never Calls for a non-admin", async () => {
    window.location.hash = "#database";
    const first = render(<WorkApp username="a" isAdmin={false} />);
    expect(await screen.findByText(/Chưa có bảng nào/)).toBeInTheDocument();
    first.unmount();
    window.location.hash = "#calls";
    render(<WorkApp username="a" isAdmin={false} />);
    expect(await screen.findByText("Thư mục này đang trống.")).toBeInTheDocument();
    window.location.hash = "";
  });

  it("starts with the header hidden, picks a theme, and Show/Hide, Theme and the links work", async () => {
    render(<WorkApp username="alice" isAdmin={false} />);
    expect(document.getElementById("page-header")).toBeNull();
    expect([...document.styleSheets].some((s) => [...s.cssRules].some((r) => (r as CSSStyleRule).selectorText === "*"))).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(document.getElementById("page-header")).not.toBeNull();
    expect(document.getElementById("page-footer")).not.toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(document.getElementById("page-header")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Theme" }));
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    for (const [name, path] of [["Home", "/"], ["Chat", "/chat"], ["alice", "/login"]]) {
      await userEvent.click(screen.getByRole("button", { name }));
      expect(assign).toHaveBeenLastCalledWith(path);
    }
    vi.unstubAllGlobals();
  });

  it("derives admin from the session role", async () => {
    sessionMock.mockResolvedValue({ id: 1, username: "a", role: "admin" } as never);
    const first = render(<Page />);
    expect(await screen.findByRole("button", { name: "Calls" })).toBeInTheDocument();
    first.unmount();
    sessionMock.mockResolvedValue({ id: 2, username: "b" });
    render(<Page />);
    await screen.findByRole("button", { name: "File" });
    expect(screen.queryByRole("button", { name: "Calls" })).toBeNull();
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
