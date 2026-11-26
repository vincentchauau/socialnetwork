import { apiFetch } from "@sn/api";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PayList from "../../app/market/orders/PayList";

vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn() }));

const api = vi.mocked(apiFetch);
const order = (id: number, status: string) => ({ id, status, currency: "USD", total_cents: 1250, buyer_username: "alice", created_at: "2025-01-01T00:00:00Z", items: [{ product_id: 1, name: "Lamp", unit_price_cents: 1250, quantity: 1, line_total_cents: 1250 }] });

beforeEach(() => {
  api.mockReset();
  api.mockImplementation(async (url: string, init?: RequestInit) => (init?.method ? order(1, "paid") : { items: [order(1, "pending_payment"), order(2, "delivered")], next_cursor: null }));
});

describe("Pay tab", () => {
  it("lists only the orders that wait for payment and pays one with a key", async () => {
    render(<PayList />);
    const pay = await screen.findByRole("button", { name: /Thanh toán/ });
    expect(screen.getAllByRole("button", { name: /Thanh toán/ })).toHaveLength(1);
    await userEvent.click(pay);
    await waitFor(() => expect(api.mock.calls.some(([url, init]) => String(url).endsWith("/orders/1/pay") && init?.method === "POST" && (init.headers as Record<string, string>)["Idempotency-Key"])).toBe(true));
    expect(await screen.findByText(/Không có đơn nào chờ/)).toBeInTheDocument();
  });

  it("cancels an order that waits", async () => {
    render(<PayList />);
    await userEvent.click(await screen.findByRole("button", { name: /Huỷ|Hủy/ }));
    await waitFor(() => expect(api.mock.calls.some(([url, init]) => String(url).endsWith("/orders/1/status") && init?.method === "PATCH")).toBe(true));
  });
});
