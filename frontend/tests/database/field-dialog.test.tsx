import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ColumnInfo, TableInfo } from "@sn/compounds/crudModel";
import { apiFetch } from "@sn/api";

import FieldDialog from "../../app/database/components/record/FieldDialog";

vi.mock("@sn/api", () => ({ apiFetch: vi.fn(), apiForm: vi.fn() }));
const api = vi.mocked(apiFetch);

const table = { name: "market_products", label: "Products", pk: ["id"], writable: true, columns: [] } as unknown as TableInfo;
const name: ColumnInfo = { name: "name", type: "string", nullable: false, readonly: false, secret: false };

beforeEach(() => api.mockReset());

describe("FieldDialog", () => {
  it("saves a changed text to the row it was opened on, by its key", async () => {
    api.mockResolvedValue({ results: [{ index: 0, ok: true }], updated: 1 });
    const user = userEvent.setup();
    render(<FieldDialog api="/api/market/records" table={table} row={{ id: 4, name: "Lamp" }} column={name} onDone={vi.fn()} onClose={vi.fn()} />);
    const input = screen.getByLabelText("name");
    await user.clear(input);
    await user.type(input, "Desk lamp");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/market/records/market_products/batch-update", expect.objectContaining({ method: "POST" })));
    const body = JSON.parse(String(api.mock.calls[0][1]?.body));
    expect(body).toEqual({ rows: [{ pk: "4", values: { name: "Desk lamp" } }] });
  });

  it("shows the refused reason and keeps the dialog open", async () => {
    api.mockResolvedValue({ results: [{ index: 0, ok: false, error: "name is too long" }], updated: 0 });
    const user = userEvent.setup();
    render(<FieldDialog api="/api/market/records" table={table} row={{ id: 4, name: "Lamp" }} column={name} onDone={vi.fn()} onClose={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("name is too long")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
