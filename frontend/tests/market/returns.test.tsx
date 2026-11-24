import { apiFetch } from "@sn/api";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Suspense } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OrderPage from "../../app/market/orders/[id]/page";

let who = "alice";
vi.mock("@sn/lib/useSession", () => ({ useSession: () => ({ status: "signed-in", user: { id: 1, username: who, group: "user" } }) }));
vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn() }));

const api = vi.mocked(apiFetch);
const order = (status: string) => ({
  id: 7, status, currency: "USD", total_cents: 900, buyer_username: "alice", created_at: "2025-01-01T00:00:00Z",
  discount_code: "SAVE10", discount_cents: 100,
  items: [{ product_id: 1, name: "Lamp", unit_price_cents: 500, quantity: 2, line_total_cents: 900, discount_cents: 100 }],
});
const params = Promise.resolve({ id: "7" });
const show = async () => { await act(async () => { render(<Suspense fallback={null}><OrderPage params={params} /></Suspense>); }); };
const patched = () => api.mock.calls.filter(([, init]) => init?.method === "PATCH").map(([, init]) => JSON.parse(String(init?.body)).status);

beforeEach(() => { api.mockReset(); who = "alice"; });

describe("order returns and discount", () => {
  it("lets the buyer ask for a return of a delivered order, and shows the discount", async () => {
    api.mockImplementation(async (_url: string, init?: RequestInit) => (init?.method === "PATCH" ? order("return_requested") : order("delivered")));
    await show();
    expect(await screen.findByText(/SAVE10/)).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Yêu cầu trả hàng" }));
    await waitFor(() => expect(patched()).toEqual(["return_requested"]));
    expect(await screen.findByText(/chờ người bán/i)).toBeInTheDocument();
  });

  it("lets the seller accept or refuse a return that was asked", async () => {
    who = "sally";
    api.mockImplementation(async () => order("return_requested"));
    await show();
    await userEvent.click(await screen.findByRole("button", { name: /Chấp nhận trả hàng/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Từ chối trả hàng" }));
    await waitFor(() => expect(patched()).toEqual(["returned", "delivered"]));
  });
});
