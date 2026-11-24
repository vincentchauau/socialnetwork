import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { TableInfo } from "@sn/compounds/crudModel";
import { apiFetch } from "@sn/api";

import TableEditor from "../../app/database/components/table/TableEditor";
import { changedValues, pathPk, rawPk } from "@sn/compounds/recordModel";

vi.mock("@sn/api", () => ({ apiFetch: vi.fn() }));
const api = vi.mocked(apiFetch);

const table: TableInfo = {
  name: "rooms", label: "Rooms", pk: ["id"], writable: true,
  columns: [
    { name: "id", type: "integer", nullable: false, readonly: true, secret: false },
    { name: "title", type: "string", nullable: true, readonly: false, secret: false },
    { name: "slug", type: "string", nullable: false, readonly: false, secret: false },
  ],
} as unknown as TableInfo;

const page = { total: 2, rows: [{ id: 7, title: "General", slug: "gen" }, { id: 9, title: "Garage", slug: "gar" }] };

beforeEach(() => {
  api.mockReset();
  api.mockResolvedValue(page);
});

describe("table helpers", () => {
  it("keys a row by its key columns, raw in a body and encoded in a path", () => {
    expect(rawPk(table, { id: 7 } as never)).toBe("7");
    expect(pathPk("a b~7")).toBe("a%20b~7");
  });

  it("sends an emptied nullable text as null and only the changed columns", () => {
    const columns = table.columns.filter((c) => !c.readonly);
    expect(changedValues(columns, { title: "  " })).toEqual({ title: null });
    expect(changedValues(columns, { slug: "x" })).toEqual({ slug: "x" });
  });
});

describe("TableEditor", () => {
  it("loads one page of rows into editable cells", async () => {
    render(<TableEditor api="/api/chat/records" table={table} database="chat" />);
    expect(await screen.findByLabelText("Row 7, title")).toHaveValue("General");
    expect(screen.getByLabelText("Row 9, slug")).toHaveValue("gar");
  });

  it("saves the changed rows in one batch, by key, and says how many were saved", async () => {
    const user = userEvent.setup();
    render(<TableEditor api="/api/chat/records" table={table} database="chat" />);
    const title = await screen.findByLabelText("Row 7, title");
    await user.clear(title);
    await user.type(title, "Lobby");
    api.mockResolvedValueOnce({ results: [{ index: 0, ok: true }], updated: 1 });
    api.mockResolvedValue(page);
    await user.click(screen.getByRole("button", { name: /save 1 change/i }));
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/chat/records/rooms/batch-update", expect.objectContaining({ method: "POST" })));
    const body = JSON.parse(String(api.mock.calls.find(([url]) => String(url).endsWith("/batch-update"))?.[1]?.body));
    expect(body).toEqual({ rows: [{ pk: "7", values: { title: "Lobby" } }] });
    expect(await screen.findByText("Saved 0 new row(s) and 1 changed row(s).")).toBeInTheDocument();
  });

  it("is read-only for a table that cannot be edited", async () => {
    api.mockResolvedValue(page);
    render(<TableEditor api="/api/chat/records" table={{ ...table, writable: false } as TableInfo} database="chat" />);
    expect(await screen.findByLabelText("Row 7, title")).toHaveAttribute("readonly");
    expect(screen.queryByRole("button", { name: /save/i })).toBeNull();
  });
});
