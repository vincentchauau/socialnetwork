import { apiFetch } from "@sn/api";
import { ConfirmHost } from "@sn/compounds/Dialogs";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OrdersPage from "../../app/market/orders/page";

vi.mock("@sn/lib/useSession", () => ({ useSession: () => ({ status: "signed-in", user: { id: 1, username: "alice", group: "user" } }) }));
vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn() }));

const api = vi.mocked(apiFetch);
const order = (id: number, status: string) => ({ id, status, currency: "USD", total_cents: 500, buyer_username: "alice", created_at: "2025-01-01T00:00:00Z", items: [{ product_id: 1, name: "Lamp", unit_price_cents: 500, quantity: 1, line_total_cents: 500 }] });

beforeEach(() => {
  api.mockReset();
  api.mockImplementation(async (url: string, init?: RequestInit) => (init?.method === "DELETE" ? undefined : { items: [order(1, "cancelled"), order(2, "paid")], next_cursor: null }));
});

describe("my orders", () => {
  it("lists the orders as cards and offers Delete only on a cancelled one, after asking", async () => {
    render(<><ConfirmHost /><OrdersPage /></>);
    expect(await screen.findByRole("link", { name: /1/ })).toBeInTheDocument();
    const buttons = screen.getAllByRole("button", { name: "Xóa đơn" });
    expect(buttons).toHaveLength(1);
    await userEvent.click(buttons[0]);
    await userEvent.click(await screen.findByRole("button", { name: /Đồng ý|OK|Xóa$/ }));
    await waitFor(() => expect(api.mock.calls.some(([url, init]) => String(url).endsWith("/orders/1") && init?.method === "DELETE")).toBe(true));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Xóa đơn" })).toBeNull());
  });
});
