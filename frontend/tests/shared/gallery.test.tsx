import { resetGalleryTables } from "@sn/compounds/galleryModel";
import { ApiError, apiFetch, apiForm, loadSession } from "@sn/api";
import GalleryView, { type GalleryConfig } from "@sn/compounds/GalleryView";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn(), apiForm: vi.fn(), loadSession: vi.fn() }));

const api = vi.mocked(apiFetch);
const col = (name: string, type: string, extra: object = {}) => ({ name, type, nullable: true, readonly: false, secret: false, ...extra });
const media = { kind: "image", preview: "/api/x/img/{pk}" };
const baseTable = {
  name: "items",
  label: "Items",
  pk: ["id"],
  writable: true,
  columns: [col("id", "int", { readonly: true }), col("name", "string"), col("status", "string"), col("note", "text"), col("owner_id", "int", { ref: { table: "users", label: "name" } }), col("pic", "string", { media })],
};
const base = "/api/x/records";
const config: GalleryConfig = { title: "name", badge: "status", image: "pic", body: "note", meta: ["owner_id"], filters: ["status"], pageSize: 2 };
const all = Array.from({ length: 3 }, (_, i) => ({ id: i + 1, name: `thing${i + 1}`, status: "done", note: "long note", owner_id: 7, pic: `p${i + 1}.png` }));
let table: Record<string, unknown> = baseTable;

let suggest: () => unknown = () => ["done", "failed"];

beforeEach(() => {
  resetGalleryTables();
  table = baseTable;
  suggest = () => ["done", "failed"];
  vi.mocked(loadSession).mockResolvedValue({ id: 1, username: "u", group: "user" });
  vi.mocked(apiForm).mockReset();
  api.mockReset();
  api.mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method) return undefined;
    if (url === `${base}/tables`) return [table];
    if (url.includes("/groups?")) return suggest();
    const params = new URL(url, "http://x").searchParams;
    const q = params.get("q") ?? "";
    const status = params.get("filter_status");
    const rows = all.filter((r) => r.name.includes(q) && (!status || r.status === status));
    const offset = Number(params.get("offset"));
    return { total: rows.length, rows: rows.slice(offset, offset + Number(params.get("limit"))), labels: { owner_id: { "7": "Ann" } } };
  });
});

const show = (props: Partial<{ config: GalleryConfig }> = {}) => render(<GalleryView api={base} table="items" config={config} {...props} />);

describe("GalleryView", () => {
  it("renders cards with image, title, badge and ref labels", async () => {
    show();
    const card = await screen.findByRole("article", { name: "thing1" });
    expect(card).toHaveTextContent("done");
    expect(card).toHaveTextContent("Ann");
    expect(card.querySelector("img")?.getAttribute("src")).toBe("/api/x/img/1");
  });

  it("pages with Load more", async () => {
    show();
    await screen.findByRole("article", { name: "thing2" });
    expect(screen.queryByRole("article", { name: "thing3" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Xem thêm|Load more/ }));
    expect(await screen.findByRole("article", { name: "thing3" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Xem thêm|Load more/ })).toBeNull();
  });

  it("searches", async () => {
    show();
    await screen.findByRole("article", { name: "thing1" });
    await userEvent.type(screen.getByRole("searchbox"), "thing3{Enter}");
    await waitFor(() => expect(screen.queryByRole("article", { name: "thing1" })).toBeNull());
    expect(screen.getByRole("article", { name: "thing3" })).toBeInTheDocument();
  });

  it("filters by a chip from the suggest route and shows none when it fails", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "failed" }));
    await waitFor(() => expect(api.mock.calls.some(([url]) => String(url).includes("filter_status=failed"))).toBe(true));
    expect(await screen.findByText(/Chưa có|Nothing here/)).toBeInTheDocument();
  });

  it("shows no chips when suggest fails", async () => {
    suggest = () => {
      throw new Error("404");
    };
    show();
    await screen.findByRole("article", { name: "thing1" });
    expect(screen.queryByRole("group")).toBeNull();
  });

  it("hides edit, delete and add when the table is read only", async () => {
    table = { ...baseTable, writable: false };
    show();
    await screen.findByRole("article", { name: "thing1" });
    expect(screen.queryByRole("button", { name: /Sửa|Edit/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Xóa|Delete/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /^(Thêm dòng|Add row)$/ })).toBeNull();
  });

  it("opens the upload dialog for create_via", async () => {
    table = { ...baseTable, create_via: "/api/x/upload" };
    show();
    await userEvent.click(await screen.findByRole("button", { name: /^(Thêm dòng|Add row)$/ }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("confirms before deleting", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: /(Xóa|Delete) thing1/ }));
    const confirm = (await screen.findAllByRole("button", { name: /Xóa|Delete/ })).at(-1)!;
    await userEvent.click(confirm);
    await waitFor(() => expect(api.mock.calls.some(([url, init]) => url === `${base}/items/1` && (init as RequestInit).method === "DELETE")).toBe(true));
  });

  it("opens the edit form", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: /(Sửa|Edit) thing1/ }));
    expect(await screen.findByRole("button", { name: /Lưu|Save/ })).toBeInTheDocument();
  });

  it("shows the empty text", async () => {
    show({ config: { ...config, emptyText: "Nothing at all" } });
    await userEvent.type(await screen.findByRole("searchbox"), "zzz{Enter}");
    expect(await screen.findByText(/Không có kết quả cho|No results for/)).toHaveTextContent("zzz");
  });
});

describe("GalleryView admin scope and add link", () => {
  const adminBase = "/api/x/records";
  const ownerConfig: GalleryConfig = { ...config, ownerColumn: "owner_id" };
  const fetched = () => api.mock.calls.map(([url]) => String(url));

  beforeEach(() => {
    window.localStorage.clear();
    api.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method) return undefined;
      if (url.endsWith("/tables")) return [table];
      if (url.includes("/groups?")) return [];
      const rows = url.startsWith(adminBase) ? all : all.slice(0, 1);
      return { total: rows.length, rows, labels: url.startsWith(adminBase) ? { owner_id: { "7": "Ann" } } : {} };
    });
  });

  const asAdmin = () => vi.mocked(loadSession).mockResolvedValue({ id: 1, username: "a", group: "admin" });
  const showOwner = () => render(<GalleryView api={base} table="items" config={ownerConfig} />);

  it("hides the toggle from non-admins", async () => {
    showOwner();
    await screen.findByRole("article", { name: "thing1" });
    expect(screen.queryByRole("checkbox", { name: /Tất cả người dùng|All users/ })).toBeNull();
  });

  it("always shows an admin everyone's rows with owner chips, and offers no toggle", async () => {
    asAdmin();
    showOwner();
    await screen.findByRole("article", { name: "thing3" });
    expect(fetched().some((url) => url.startsWith(`${adminBase}/items?`))).toBe(true);
    expect(screen.getAllByTestId("owner-chip")[0]).toHaveTextContent("Ann");
    expect(screen.queryByRole("checkbox", { name: /Tất cả người dùng|All users/ })).toBeNull();
  });

  it("has no toggle when the api does not end with /data", async () => {
    asAdmin();
    render(<GalleryView api="/api/x/other" table="items" config={ownerConfig} />);
    await screen.findByRole("article", { name: "thing1" });
    expect(screen.queryByRole("checkbox", { name: /Tất cả người dùng|All users/ })).toBeNull();
  });

  it("renders Add as a link to addHref and opens no create form", async () => {
    render(<GalleryView api={base} table="items" config={{ ...config, addHref: "/video", addLabel: "New video" }} />);
    const link = await screen.findByRole("link", { name: "New video" });
    expect(link).toHaveAttribute("href", "/video");
    await userEvent.click(link);
    expect(screen.queryByRole("button", { name: /Lưu|Save/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /^(Thêm dòng|Add row)$/ })).toBeNull();
  });
});

describe("GalleryView actions, rename, de-dup and createSlot", () => {
  it("runs a custom action with the row and a context, confirms first, and reloads", async () => {
    const run = vi.fn(async (_row: unknown, ctx: { reload(): void }) => ctx.reload());
    show({ config: { ...config, pageSize: 5, actions: [{ key: "go", label: "Go", run, confirm: "Sure?" }, { key: "hid", label: "Hidden", run: vi.fn(), visible: () => false }] } });
    await userEvent.click(await screen.findByRole("button", { name: /^Go: thing1/ }));
    expect(run).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /^Hidden/ })).toBeNull();
    const listCalls = () => api.mock.calls.filter(([url]) => String(url).startsWith(`${base}/items?`)).length;
    const before = listCalls();
    await userEvent.click(screen.getByRole("button", { name: "Go" }));
    await waitFor(() => expect(run).toHaveBeenCalledTimes(1));
    expect(run.mock.calls[0][0]).toMatchObject({ id: 1, name: "thing1" });
    expect(run.mock.calls[0][1]).toMatchObject({ api: base, table: "items" });
    await waitFor(() => expect(listCalls()).toBeGreaterThan(before));
  });

  it("shows a failing action's message in the card as an alert and is busy while running", async () => {
    let fail: (e: Error) => void = () => undefined;
    const run = () => new Promise<void>((_, reject) => { fail = reject; });
    show({ config: { ...config, actions: [{ key: "x", label: "Boom", run }] } });
    const button = await screen.findByRole("button", { name: /^Boom: thing1/ });
    await userEvent.click(button);
    expect(button).toBeDisabled();
    fail(new ApiError(400, "it broke"));
    const card = screen.getByRole("article", { name: "thing1" });
    expect(await within(card).findByRole("alert")).toHaveTextContent("it broke");
    expect(button).toBeEnabled();
  });

  it("renames the title in place: Enter saves with PATCH, Escape cancels", async () => {
    show({ config: { ...config, renameColumn: "name" } });
    await userEvent.click(await screen.findByRole("button", { name: /^(Đổi tên|Rename): thing1/ }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("textbox", { name: /Tên mới|New name/ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /^(Đổi tên|Rename): thing1/ }));
    const field = screen.getByRole("textbox", { name: /Tên mới|New name/ });
    await userEvent.clear(field);
    await userEvent.type(field, "renamed{Enter}");
    await waitFor(() => expect(api).toHaveBeenCalledWith(`${base}/items/1`, { method: "PATCH", body: JSON.stringify({ values: { name: "renamed" } }) }));
    expect(await screen.findByRole("article", { name: "renamed" })).toBeInTheDocument();
  });

  it("restores the title and shows the error when the rename fails", async () => {
    const original = api.getMockImplementation()!;
    api.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "PATCH") throw new ApiError(400, "nope");
      return original(url, init);
    });
    show({ config: { ...config, renameColumn: "name" } });
    await userEvent.click(await screen.findByRole("button", { name: /^(Đổi tên|Rename): thing1/ }));
    await userEvent.type(screen.getByRole("textbox", { name: /Tên mới|New name/ }), "x{Enter}");
    const card = screen.getByRole("article", { name: "thing1" });
    expect(await within(card).findByRole("alert")).toHaveTextContent("nope");
  });

  it("shows no rename when the table cannot be edited", async () => {
    table = { ...baseTable, writable: false };
    show({ config: { ...config, renameColumn: "name" } });
    await screen.findByRole("article", { name: "thing1" });
    expect(screen.queryByRole("button", { name: /^(Đổi tên|Rename)/ })).toBeNull();
  });

  it("does not repeat the title as body or subtitle", async () => {
    show({ config: { ...config, body: "name", subtitle: "name" } });
    const card = await screen.findByRole("article", { name: "thing1" });
    expect(within(card).getAllByText("thing1")).toHaveLength(1);
  });

  it("renders createSlot above the toolbar, with a reload that refreshes the cards", async () => {
    show({ config: { ...config, hideAdd: true, pageSize: 5 } });
    cleanup();
    render(<GalleryView api={base} table="items" config={{ ...config, hideAdd: true, pageSize: 5 }} createSlot={(reload) => <button type="button" onClick={reload}>Make</button>} />);
    await screen.findByRole("article", { name: "thing1" });
    const make = screen.getByRole("button", { name: "Make" });
    expect(make.compareDocumentPosition(screen.getByRole("search")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^(Thêm dòng|Add row)$/ })).toBeNull();
    const listCalls = () => api.mock.calls.filter(([url]) => String(url).startsWith(`${base}/items?`)).length;
    const before = listCalls();
    await userEvent.click(make);
    await waitFor(() => expect(listCalls()).toBeGreaterThan(before));
  });
});
