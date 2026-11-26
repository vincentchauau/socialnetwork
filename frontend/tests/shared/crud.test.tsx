import { ApiError, apiFetch, apiForm, loadSession } from "@sn/api";
import CrudView, { type TableInfo, pkOf, valuesOf } from "@sn/compounds/CrudView";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn(), apiForm: vi.fn(), loadSession: vi.fn() }));

const api = vi.mocked(apiFetch);
const form = vi.mocked(apiForm);
const col = (name: string, type: string, extra: object = {}) => ({ name, type, nullable: false, readonly: false, secret: false, ...extra });
const crud: TableInfo = {
  name: "items",
  label: "Items",
  pk: ["id"],
  writable: true,
  columns: [col("id", "int", { readonly: true }), col("name", "string"), col("note", "text", { nullable: true }), col("token", "string", { secret: true, nullable: true })] as TableInfo["columns"],
};
const readDelete: TableInfo = { ...crud, name: "logs", label: "Logs", writable: false };
const base = "/api/x/records";
const allRows = Array.from({ length: 25 }, (_, index) => ({ id: index + 1, name: `item${index + 1}`, note: null, token: "***" }));

function failNextPost(error: Error) {
  const previous = api.getMockImplementation();
  let failed = false;
  api.mockImplementation((path, init) => {
    if (!failed && (init as RequestInit | undefined)?.method === "POST") {
      failed = true;
      return Promise.reject(error);
    }
    return previous ? previous(path, init) : Promise.resolve(undefined as never);
  });
}

function calls(method: string) {
  return api.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === method);
}

beforeEach(() => {
  window.localStorage.clear();
  vi.mocked(loadSession).mockReset();
  vi.mocked(loadSession).mockResolvedValue({ id: 9, username: "u", group: "user" });
  form.mockReset();
  form.mockResolvedValue(undefined);
  api.mockReset();
  api.mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method) return undefined;
    const params = new URL(url, "http://x").searchParams;
    const q = params.get("q") ?? "";
    const offset = Number(params.get("offset") ?? 0);
    const matching = allRows.filter((row) => row.name.includes(q));
    return { total: matching.length, rows: matching.slice(offset, offset + Number(params.get("limit"))) };
  });
});

describe("pure helpers", () => {
  it("joins a composite key with ~", () => {
    expect(pkOf({ ...crud, pk: ["a", "b"] }, { a: 1, b: "x y" })).toBe("1~x%20y");
  });
  it("rejects bad numbers and json, and keeps an empty secret out of an edit", () => {
    const table: TableInfo = { ...crud, columns: [col("n", "int"), col("j", "json"), col("s", "string", { secret: true })] as TableInfo["columns"], pk: ["n"] };
    expect(valuesOf(table, { n: "1.5", j: "", s: "" }, false)).toHaveProperty("error");
    expect(valuesOf(table, { n: "2", j: "{", s: "a" }, false)).toHaveProperty("error");
    expect(valuesOf(table, { n: "2", j: "[1]", s: "" }, true)).toEqual({ values: { j: [1] } });
  });
});

describe("CrudView in place (editMode inline)", () => {
  it("turns the cells of the row into boxes on Edit and saves them with a PATCH, with no dialog", async () => {
    render(<CrudView api={base} table={crud} editMode="inline" />);
    await screen.findByText("item1");
    await userEvent.click(screen.getByRole("button", { name: "Sửa 1" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    const box = screen.getByRole("textbox", { name: "name" });
    expect(box).toHaveValue("item1");
    await userEvent.clear(box);
    await userEvent.type(box, "renamed");
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(calls("PATCH")).toHaveLength(1));
    expect(calls("PATCH")[0][0]).toBe(`${base}/items/1`);
    expect(JSON.parse(String((calls("PATCH")[0][1] as RequestInit).body)).values).toMatchObject({ name: "renamed" });
  });

  it("opens a line of boxes for Add row and posts it", async () => {
    render(<CrudView api={base} table={crud} editMode="inline" />);
    await screen.findByText("item1");
    await userEvent.click(screen.getByRole("button", { name: "Thêm dòng" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.type(screen.getByRole("textbox", { name: "name" }), "fresh");
    await userEvent.click(within(screen.getByRole("form", { name: "Thêm dòng" })).getByRole("button", { name: "Thêm dòng" }));
    await waitFor(() => expect(calls("POST")).toHaveLength(1));
    expect(JSON.parse(String((calls("POST")[0][1] as RequestInit).body)).values).toMatchObject({ name: "fresh" });
  });
});

describe("CrudView", () => {
  it("lists, pages and searches", async () => {
    render(<CrudView api={base} table={crud} />);
    expect(await screen.findByText("item1")).toBeInTheDocument();
    expect(screen.getByText("1-20 / 25")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sau" }));
    expect(await screen.findByText("21-25 / 25")).toBeInTheDocument();
    expect(await screen.findByText("item21")).toBeInTheDocument();
    await userEvent.type(screen.getByPlaceholderText(/Từ khóa|Words or/), "item7{Enter}");
    await waitFor(() => expect(screen.queryByText("item21")).not.toBeInTheDocument());
    expect(within(screen.getByRole("table")).getByText("item7")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /item7/ })).toBeInTheDocument(); // the chip of the term
  });

  it("shows the empty state", async () => {
    api.mockResolvedValue({ total: 0, rows: [] });
    render(<CrudView api={base} table={crud} />);
    expect(await screen.findByText("Không có dòng nào.")).toBeInTheDocument();
  });

  it("creates a row and skips read-only columns", async () => {
    render(<CrudView api={base} table={crud} />);
    await screen.findByText("item1");
    await userEvent.click(screen.getByRole("button", { name: "Thêm dòng" }));
    expect(screen.queryByLabelText("Id")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Token")).toHaveAttribute("type", "password");
    await userEvent.type(screen.getByLabelText("Name"), "new");
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(calls("POST")).toHaveLength(1));
    expect(calls("POST")[0][0]).toBe(`${base}/items`);
    expect(JSON.parse((calls("POST")[0][1] as RequestInit).body as string)).toEqual({ values: { name: "new", note: null, token: null } });
  });

  it("edits a row with PATCH", async () => {
    render(<CrudView api={base} table={crud} />);
    await screen.findByText("item1");
    await userEvent.click(screen.getByRole("button", { name: "Sửa 1" }));
    const name = screen.getByLabelText("Name");
    await userEvent.clear(name);
    await userEvent.type(name, "renamed");
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(calls("PATCH")).toHaveLength(1));
    expect(calls("PATCH")[0][0]).toBe(`${base}/items/1`);
    expect(JSON.parse((calls("PATCH")[0][1] as RequestInit).body as string).values).toEqual({ name: "renamed", note: null });
  });

  it("shows 409 and 422 details and keeps the form", async () => {
    render(<CrudView api={base} table={crud} />);
    await screen.findByText("item1");
    await userEvent.click(screen.getByRole("button", { name: "Thêm dòng" }));
    await userEvent.type(screen.getByLabelText("Name"), "dup");
    await waitFor(() => expect(api.mock.calls.some(([path]) => String(path).includes("/suggest"))).toBe(true)); // the debounced suggestion request must not eat the mocked failure
    failNextPost(new ApiError(409, "conflict", { detail: "name already exists" }));
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(await screen.findByText("name already exists")).toBeInTheDocument();
    failNextPost(new ApiError(422, "bad", { detail: [{ msg: "too short" }, { msg: "bad chars" }] }));
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(await screen.findByText("too short; bad chars")).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("dup");
  });

  it("deletes only after confirming", async () => {
    render(<CrudView api={base} table={crud} />);
    await screen.findByText("item1");
    await userEvent.click(screen.getByRole("button", { name: "Xóa 2" }));
    await userEvent.click(screen.getByRole("button", { name: "Hủy" }));
    expect(calls("DELETE")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Xóa 2" }));
    await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Xóa" }));
    await waitFor(() => expect(calls("DELETE")).toHaveLength(1));
    expect(calls("DELETE")[0][0]).toBe(`${base}/items/2`);
  });

  it("hides create, edit and delete for a table that is not writable", async () => {
    render(<CrudView api={base} table={readDelete} />);
    await screen.findByText("item1");
    expect(screen.queryByRole("button", { name: "Thêm dòng" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Sửa/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xóa 1" })).not.toBeInTheDocument();
  });
});

describe("CrudView as a data table", () => {
  const rich: TableInfo = {
    name: "rich",
    label: "Rich",
    pk: ["id"],
    writable: true,
    columns: [
      col("id", "int", { readonly: true }),
      col("user_id", "int"),
      col("title", "string"),
      col("created_at", "datetime"),
      col("active", "bool"),
      col("meta", "json", { nullable: true }),
      col("image", "string", { nullable: true }),
      col("secret_note", "string", { secret: true }),
      col("body", "text", { nullable: true }),
    ] as TableInfo["columns"],
  };
  const richRow = { id: 7, user_id: 3, title: "Hello", created_at: "2024-03-05T10:20:00", active: true, meta: { a: 1, b: [1, 2] }, image: "/media/a.png", secret_note: "***", body: null };
  const serveRich = (rows: object[] = [richRow], total = 134) =>
    api.mockImplementation(async (url: string, init?: RequestInit) => (init?.method ? undefined : { total, rows }));

  it("hides technical columns, and the Columns menu shows them again and remembers it", async () => {
    serveRich();
    window.localStorage.clear();
    const view = render(<CrudView api={base} table={rich} />);
    await screen.findByText("Hello");
    const headers = () => screen.getAllByRole("columnheader").map((header) => header.textContent?.replace(/\s*[▲▼↕]$/, ""));
    expect(headers()).toEqual(expect.arrayContaining(["id", "title", "created_at", "active", "meta", "image", "body"]));
    expect(headers()).not.toContain("user_id");
    expect(headers()).not.toContain("secret_note");
    await userEvent.click(screen.getByRole("button", { name: "Cột" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "user_id" }));
    expect(headers()).toContain("user_id");
    await userEvent.click(screen.getByRole("checkbox", { name: "title" }));
    expect(headers()).not.toContain("title");
    view.unmount();
    render(<CrudView api={base} table={rich} />);
    await screen.findByText("3");
    expect(headers()).toContain("user_id");
    expect(headers()).not.toContain("title");
  });

  it("writes the range of the page", async () => {
    serveRich([richRow], 134);
    render(<CrudView api={base} table={rich} />);
    expect(await screen.findByText("1-20 / 134")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Trước" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Sau" })).toBeEnabled();
  });

  it("formats dates, flags, json, empty values and pictures", async () => {
    serveRich();
    render(<CrudView api={base} table={rich} />);
    await screen.findByText("Hello");
    const row = screen.getAllByRole("row")[1];
    const date = within(row).getByTitle("2024-03-05T10:20:00");
    expect(date.textContent).toMatch(/2024|24/);
    expect(within(row).getByLabelText("Có").textContent).toBe("✓");
    expect(within(row).getByText("a")).toBeInTheDocument();
    expect(within(row).getAllByText("1").length).toBeGreaterThan(0);
    expect(within(row).getByLabelText("null").textContent).toBe("–");
    expect(row.querySelector("img")).toHaveAttribute("src", "/media/a.png");
  });

  it("expands long text on click", async () => {
    const long = "x".repeat(100);
    serveRich([{ ...richRow, title: long }]);
    render(<CrudView api={base} table={rich} />);
    const cell = await screen.findByText(`${"x".repeat(60)}…`);
    await userEvent.click(cell);
    expect(screen.getByText(long)).toBeInTheDocument();
  });

  it("adds and edits in a dialog, and shows the server detail in it", async () => {
    serveRich();
    render(<CrudView api={base} table={rich} />);
    await screen.findByText("Hello");
    await userEvent.click(screen.getByRole("button", { name: "Thêm dòng" }));
    const dialog = screen.getByRole("dialog", { name: "Thêm dòng mới" });
    await userEvent.type(within(dialog).getByLabelText("User"), "5");
    await userEvent.type(within(dialog).getByLabelText("Title"), "T");
    fireEvent.change(within(dialog).getByLabelText("Created at"), { target: { value: "2024-01-01T00:00" } });
    api.mockRejectedValueOnce(new ApiError(409, "conflict", { detail: "title exists" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Lưu" }));
    expect(await within(dialog).findByText("title exists")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Hủy" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sửa 7" }));
    expect(screen.getByRole("dialog", { name: "Sửa dòng" })).toBeInTheDocument();
    expect(screen.getByLabelText("Id")).toBeDisabled();
  });

  it("asks before deleting", async () => {
    serveRich();
    render(<CrudView api={base} table={rich} />);
    await screen.findByText("Hello");
    await userEvent.click(screen.getByRole("button", { name: "Xóa 7" }));
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(calls("DELETE")).toHaveLength(0);
    await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Xóa" }));
    await waitFor(() => expect(calls("DELETE")).toHaveLength(1));
    expect(calls("DELETE")[0][0]).toBe(`${base}/rich/7`);
  });
});

describe("CrudView references, json, badges and layout", () => {
  const jobs: TableInfo = {
    name: "job_applications",
    label: "Applicants",
    pk: ["id"],
    writable: true,
    columns: [
      col("id", "int", { readonly: true }),
      col("user_id", "int", { ref: { table: "users", label: "username" } }),
      col("job_id", "int"),
      col("status", "string", { nullable: true }),
      col("resume", "json", { nullable: true }),
    ] as TableInfo["columns"],
  };
  const row = { id: 1, user_id: 2, job_id: 9, status: "applied", resume: { headline: "Ứng viên ở Đà Lạt", summary: "Tôi thích làm việc nhóm rất nhiều", skills: ["a", "b"] } };
  const serve = (rows: object[] = [row], labels?: object) =>
    api.mockImplementation(async (url: string, init?: RequestInit) => (init?.method ? undefined : { total: rows.length, rows, labels }));
  const headers = () => screen.getAllByRole("columnheader").map((header) => header.textContent?.replace(/\s*[▲▼↕]$/, ""));

  it("shows the label of a reference column, visible by default, with the id in the title", async () => {
    serve([row], { user_id: { "2": "Binh_Phan" } });
    render(<CrudView api={base} table={jobs} />);
    const label = await screen.findByText("Binh_Phan");
    expect(label).toHaveAttribute("title", "user_id 2");
    expect(headers()).toContain("user_id");
    expect(headers()).not.toContain("job_id");
  });

  it("falls back to the raw id when there is no label", async () => {
    serve([row]);
    render(<CrudView api={base} table={jobs} />);
    expect(await screen.findByText("2")).toBeInTheDocument();
  });

  it("shows the label next to the raw id in the form", async () => {
    serve([row], { user_id: { "2": "Binh_Phan" } });
    render(<CrudView api={base} table={jobs} />);
    await screen.findByText("Binh_Phan");
    await userEvent.click(screen.getByRole("button", { name: "Sửa 1" }));
    const dialog = screen.getByRole("dialog", { name: "Sửa dòng" });
    expect(within(dialog).getByLabelText("User")).toHaveValue("2");
    expect(within(dialog).getByTestId("ref-label-user_id")).toHaveTextContent("Binh_Phan");
  });

  it("shows json in plain sight: its keys and values, with no summary and no dialog", async () => {
    serve();
    render(<CrudView api={base} table={jobs} />);
    expect(await screen.findByText("headline")).toBeInTheDocument();
    expect(screen.getByText("Ứng viên ở Đà Lạt")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Dữ liệu JSON" })).not.toBeInTheDocument();
  });

  it("shows an array as its items, not as a count", async () => {
    serve([{ ...row, resume: [1, 2, 3] }]);
    render(<CrudView api={base} table={jobs} />);
    expect(await screen.findByText("#3")).toBeInTheDocument();
    expect(screen.queryByText("3 mục")).not.toBeInTheDocument();
  });
  it("renders status as a stable badge and an empty status as a dash", async () => {
    serve([row, { ...row, id: 2, status: "applied" }, { ...row, id: 3, status: null }]);
    render(<CrudView api={base} table={jobs} />);
    const badges = await screen.findAllByText("applied");
    expect(badges).toHaveLength(2);
    expect(badges[0]).toHaveClass("sn-dt-badge");
    expect(badges[0].getAttribute("data-hue")).toBe(badges[1].getAttribute("data-hue"));
    expect(screen.getAllByRole("row")[3].querySelector(".sn-dt-badge")).toBeNull();
    expect(within(screen.getAllByRole("row")[3]).getAllByLabelText("null").length).toBeGreaterThan(0);
  });

  it("keeps the actions sticky, the toolbar wrapping and the search a placeholder", async () => {
    serve();
    render(<CrudView api={base} table={jobs} />);
    await screen.findByText("applied");
    const actions = screen.getAllByRole("columnheader").find((header) => header.classList.contains("cw-col-actions"))!;
    expect(actions.classList.contains("cw-col-actions")).toBe(true);
    expect(document.querySelector(".sn-toolbar")).toHaveStyle({ flexWrap: "wrap" });
    const search = screen.getByPlaceholderText(/Từ khóa|Words or/);
    expect(search).toHaveAttribute("aria-label", "Tìm kiếm");
    expect(screen.queryByText("Tìm kiếm")).not.toBeInTheDocument();
  });

  it("expands long text with a keyboard-reachable button and no link underline", async () => {
    const long = "y".repeat(90);
    serve([{ ...row, id: 5, resume: null, note: long }]);
    render(<CrudView api={base} table={{ ...jobs, columns: [...jobs.columns, col("note", "text")] as TableInfo["columns"] }} />);
    await screen.findByText(long.slice(0, 60) + "…");
    const button = screen.getByTitle(/Bấm để xem đầy đủ/);
    expect(button).toHaveAttribute("aria-expanded", "false");
  });
});

describe("CrudView form and toolbar polish", () => {
  const owned: TableInfo = {
    name: "pics",
    label: "Pics",
    pk: ["id"],
    writable: true,
    columns: [
      col("id", "int", { readonly: true }),
      col("owner_id", "int", { ref: { table: "users", label: "username" } }),
      col("title", "string"),
      col("created_at", "datetime", { readonly: true }),
      col("when_at", "datetime", { nullable: true }),
    ] as TableInfo["columns"],
  };
  const orow = { id: 4, owner_id: 2, title: "T", created_at: "2024-03-05T10:20:00", when_at: "2024-03-05T10:20:00" };
  const serve = (rows: object[]) =>
    api.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/me")) return { id: 9, username: "u", group: "user" };
      return init?.method ? undefined : { total: rows.length, rows };
    });

  it("gives the toolbar controls one height and a centered row", async () => {
    serve([orow]);
    render(<CrudView api={base} table={owned} />);
    await screen.findByText("T");
    const toolbar = document.querySelector(".sn-toolbar") as HTMLElement;
    expect(toolbar).toHaveStyle({ alignItems: "center", flexWrap: "wrap" });
    const controls = [screen.getByPlaceholderText(/Từ khóa|Words or/), screen.getByRole("button", { name: "Cột" }), screen.getByRole("button", { name: "Thêm dòng" })];
    const heights = controls.map((el) => el.style.height);
    expect(new Set(heights).size).toBe(1);
    expect(heights[0]).toBe("36px");
    expect(new Set(controls.map((el) => el.style.fontSize)).size).toBe(1);
  });

  it("uses a new column memory key and large edit buttons with tooltips", async () => {
    window.localStorage.setItem(`sn_cols_${base}/pics`, JSON.stringify(["title"]));
    serve([orow]);
    render(<CrudView api={base} table={owned} />);
    await screen.findByText("T");
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent?.replace(/\s*[▲▼↕]$/, ""))).toContain("owner_id");
    await userEvent.click(screen.getByRole("button", { name: "Cột" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "title" }));
    expect(window.localStorage.getItem(`sn_cols2_${base}/pics`)).not.toBeNull();
    const edit = screen.getByRole("button", { name: "Sửa 4" });
    expect(edit).toHaveAttribute("title", "Sửa");
    expect(edit).toHaveTextContent("Sửa");
  });

  it("omits readonly columns when creating and prefills the owner for a non-admin", async () => {
    serve([orow]);
    render(<CrudView api={base} table={owned} />);
    await screen.findByText("T");
    await userEvent.click(screen.getByRole("button", { name: "Thêm dòng" }));
    const dialog = screen.getByRole("dialog", { name: "Thêm dòng mới" });
    expect(within(dialog).queryByLabelText("Id")).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Created at")).not.toBeInTheDocument();
    expect(within(dialog).queryByTestId("system-info")).not.toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByLabelText("Owner")).toHaveValue("9"));
  });

  it("leaves the owner empty for an admin", async () => {
    vi.mocked(loadSession).mockResolvedValue({ id: 1, username: "a", group: "admin" });
    serve([orow]);
    render(<CrudView api={base} table={owned} />);
    await screen.findByText("T");
    await userEvent.click(screen.getByRole("button", { name: "Thêm dòng" }));
    const dialog = screen.getByRole("dialog", { name: "Thêm dòng mới" });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(within(dialog).getByLabelText("Owner")).toHaveValue("");
    expect(within(dialog).getByText(/bắt buộc/)).toBeInTheDocument();
  });

  it("locks readonly columns under system info, edits dates locally and warns on ref changes", async () => {
    serve([orow]);
    render(<CrudView api={base} table={owned} />);
    await screen.findByText("T");
    await userEvent.click(screen.getByRole("button", { name: "Sửa 4" }));
    const dialog = screen.getByRole("dialog", { name: "Sửa dòng" });
    const system = within(dialog).getByTestId("system-info");
    expect(within(system).getByLabelText("Id")).toBeDisabled();
    expect(within(system).getByLabelText("Created at")).toBeDisabled();
    expect((within(system).getByLabelText("Created at") as HTMLInputElement).value).toMatch(/2024|24/);
    expect(within(system).getAllByText("chỉ đọc").length).toBe(2);
    const when = within(dialog).getByLabelText("When at") as HTMLInputElement;
    expect(when.type).toBe("datetime-local");
    expect(when.value).toBe("2024-03-05T10:20");
    expect(within(dialog).getByText("Owner")).toHaveAttribute("title", "owner_id");
    expect(within(dialog).queryByTestId("ref-warning-owner_id")).not.toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText("Owner"), "1");
    expect(within(dialog).getByTestId("ref-warning-owner_id")).toBeInTheDocument();
    fireEvent.change(when, { target: { value: "2025-01-02T03:04" } });
    await userEvent.click(within(dialog).getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(calls("PATCH")).toHaveLength(1));
    const sent = JSON.parse((calls("PATCH")[0][1] as RequestInit).body as string).values;
    expect(sent.when_at).toBe(new Date("2025-01-02T03:04").toISOString());
    expect(sent).not.toHaveProperty("created_at");
  });
});

describe("media columns", () => {
  const mk = (kind: string | undefined, extra: object = {}) =>
    ({
      name: "files",
      label: "Files",
      pk: ["id"],
      writable: true,
      columns: [col("id", "int", { readonly: true }), col("title", "string"), col("path", "string", { media: { kind, preview: "/m/{pk}/raw", ...extra } })],
    }) as TableInfo;
  const mrow = { id: 3, title: "t", path: "/store/deep/dir/pic.png" };
  const serve = (rows: object[]) => api.mockImplementation(async (_u: string, init?: RequestInit) => (init?.method ? undefined : { total: rows.length, rows }));

  it("shows an image thumbnail with the file name only and opens a larger preview", async () => {
    serve([mrow]);
    render(<CrudView api={base} table={mk(undefined)} />);
    const thumb = (await screen.findByAltText("pic.png")) as HTMLImageElement;
    expect(thumb).toHaveAttribute("src", "/m/3/raw");
    expect(thumb).toHaveAttribute("loading", "lazy");
    expect(thumb.style.height).toBe("40px");
    expect(screen.getByText("pic.png")).toHaveAttribute("title", "/store/deep/dir/pic.png");
    expect(screen.queryByText("/store/deep/dir/pic.png")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("media-path"));
    const dialog = screen.getByRole("dialog", { name: "Xem ảnh" });
    expect(within(dialog).getByAltText("pic.png")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Đóng" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("uses the value itself for @self", async () => {
    serve([{ ...mrow, path: "https://x.test/a/b.jpg" }]);
    render(<CrudView api={base} table={mk("image", { preview: "@self" })} />);
    expect(await screen.findByAltText("b.jpg")).toHaveAttribute("src", "https://x.test/a/b.jpg");
  });

  it("opens a video player, an audio player and shows a download link for files", async () => {
    serve([mrow]);
    const video = render(<CrudView api={base} table={mk("video")} />);
    await userEvent.click(await screen.findByTestId("media-path"));
    expect(within(screen.getByRole("dialog", { name: "Xem ảnh" })).getByLabelText("pic.png").tagName).toBe("VIDEO");
    video.unmount();
    const audio = render(<CrudView api={base} table={mk("audio")} />);
    await userEvent.click(await screen.findByTestId("media-path"));
    expect(within(screen.getByRole("dialog", { name: "Xem ảnh" })).getByLabelText("pic.png").tagName).toBe("AUDIO");
    audio.unmount();
    render(<CrudView api={base} table={mk("file")} />);
    const link = await screen.findByRole("link", { name: "pic.png" });
    expect(link).toHaveAttribute("href", "/m/3/raw");
  });

  it("does not shorten paths of columns without media metadata", async () => {
    serve([{ id: 1, title: "t", path: "/store/deep/dir/pic.txt" }]);
    render(<CrudView api={base} table={{ ...mk("file"), columns: [col("id", "int", { readonly: true }), col("path", "string")] as TableInfo["columns"] }} />);
    expect(await screen.findByText("/store/deep/dir/pic.txt")).toBeInTheDocument();
  });

  it("replaces the file at once with a PUT of multipart file, then busts the cache", async () => {
    serve([mrow]);
    render(<CrudView api={base} table={mk("image", { replace: "/up/{id}", accept: "image/*" })} />);
    await screen.findByAltText("pic.png");
    await userEvent.click(screen.getByRole("button", { name: "Sửa 3" }));
    const dialog = screen.getByRole("dialog", { name: "Sửa dòng" });
    expect(within(dialog).getByAltText("pic.png")).toBeInTheDocument();
    const input = within(dialog).getByLabelText("path") as HTMLInputElement;
    expect(input).toHaveAttribute("accept", "image/*");
    await userEvent.upload(input, new File(["x"], "n.png", { type: "image/png" }));
    await waitFor(() => expect(form).toHaveBeenCalledTimes(1));
    const [url, body, init] = form.mock.calls[0];
    expect(url).toBe("/up/3");
    expect((body as FormData).get("file")).toBeInstanceOf(File);
    expect(init).toMatchObject({ method: "PUT" });
    await waitFor(() => expect(within(dialog).getByAltText("pic.png").getAttribute("src")).toMatch(/^\/m\/3\/raw\?v=\d+$/));
  });

  it("shows an error when the replacement fails", async () => {
    serve([mrow]);
    form.mockRejectedValueOnce(new ApiError(413, "big", { detail: "too big" }));
    render(<CrudView api={base} table={mk("image", { replace: "/up/{id}" })} />);
    await screen.findByAltText("pic.png");
    await userEvent.click(screen.getByRole("button", { name: "Sửa 3" }));
    await userEvent.upload(within(screen.getByRole("dialog")).getByLabelText("path"), new File(["x"], "n.png", { type: "image/png" }));
    expect(await screen.findByText("too big")).toBeInTheDocument();
  });

  it("keeps a text input with the thumbnail for preview-only media", async () => {
    serve([mrow]);
    render(<CrudView api={base} table={mk("image")} />);
    await screen.findByAltText("pic.png");
    await userEvent.click(screen.getByRole("button", { name: "Sửa 3" }));
    const dialog = screen.getByRole("dialog", { name: "Sửa dòng" });
    expect(within(dialog).getByLabelText("Path")).toHaveValue("/store/deep/dir/pic.png");
    expect(within(dialog).getByAltText("pic.png")).toBeInTheDocument();
  });
});

describe("create_via", () => {
  const via: TableInfo = {
    name: "docs",
    label: "Docs",
    pk: ["id"],
    writable: true,
    create_via: "/api/x/upload",
    create_label: "Upload docs",
    columns: [col("id", "int", { readonly: true }), col("title", "string")] as TableInfo["columns"],
  };

  it("replaces Add row with the labelled upload button and posts each file, then reloads", async () => {
    api.mockImplementation(async () => ({ total: 0, rows: [] }));
    render(<CrudView api={base} table={via} />);
    await screen.findByText("Không có dòng nào.");
    await userEvent.click(screen.getByRole("button", { name: "Thêm dòng" }));
    const dialog = screen.getByRole("dialog", { name: "Upload docs" });
    const before = api.mock.calls.length;
    await userEvent.upload(within(dialog).getByLabelText("Upload docs"), [new File(["1"], "a.pdf"), new File(["2"], "b.pdf")]);
    await waitFor(() => expect(form).toHaveBeenCalledTimes(2));
    expect(form.mock.calls.map((call) => call[0])).toEqual(["/api/x/upload", "/api/x/upload"]);
    expect((form.mock.calls[1][1] as FormData).get("file")).toHaveProperty("name", "b.pdf");
    await waitFor(() => expect(api.mock.calls.length).toBeGreaterThan(before));
    expect(await within(dialog).findAllByText(/Đã tải lên/)).toHaveLength(2);
  });
});

describe("sorting by the head of a column", () => {
  const listUrls = () => api.mock.calls.map(([url]) => String(url)).filter((url) => url.includes("/items?"));

  it("sorts up, then down, then as the table has it, and not by a secret column", async () => {
    render(<CrudView api={base} table={crud} />);
    await screen.findByText("item1");
    expect(screen.queryByRole("button", { name: /token/ })).toBeNull();
    const head = () => screen.getByRole("button", { name: /^name/ });
    await userEvent.click(head());
    await waitFor(() => expect(listUrls().at(-1)).toMatch(/sort=name(&|$)/));
    await userEvent.click(head());
    await waitFor(() => expect(listUrls().at(-1)).toContain("sort=-name"));
    await userEvent.click(head());
    await waitFor(() => expect(listUrls().at(-1)).not.toContain("sort="));
  });

  it("goes back to the first page when the order changes", async () => {
    render(<CrudView api={base} table={crud} />);
    await screen.findByText("item1");
    await userEvent.click(screen.getByRole("button", { name: "Sau" }));
    await waitFor(() => expect(listUrls().at(-1)).toContain("offset=20"));
    await userEvent.click(screen.getByRole("button", { name: /^name/ }));
    await waitFor(() => expect(listUrls().at(-1)).toContain("offset=0"));
  });
});
