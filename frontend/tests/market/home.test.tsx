import { apiFetch } from "@sn/api";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ShopPage from "../_pages/market";

vi.mock("@sn/lib/useSession", () => ({ useSession: () => ({ status: "signed-in", user: { id: 1, username: "alice", group: "user" } }) }));
vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn() }));

const api = vi.mocked(apiFetch);
const product = (id: number, name: string, extra = {}) => ({ id, seller_id: 2, seller_username: "bob", name, description: "", price_cents: 1250, currency: "USD", stock: 3, image_url: null, category: "home", rating_average: null, review_count: 0, created_at: "2025-01-01T00:00:00Z", ...extra });

beforeEach(() => {
  window.localStorage.clear();
  api.mockReset();
  api.mockImplementation(async (url: string) => {
    if (url.endsWith("/categories")) return [{ name: "home", count: 2 }, { name: "toys", count: 1 }];
    return { items: [product(1, "Lamp", { rating_average: 4.5, review_count: 2 }), product(2, "Chair")], next_cursor: null };
  });
});

describe("the market", () => {
  it("shows the products as cards with their price and stars, beside a tree of the categories", async () => {
    render(<ShopPage />);
    expect(await screen.findByRole("link", { name: "Lamp" })).toHaveAttribute("href", "/market/products/1");
    expect(screen.getAllByText("$12.50")).toHaveLength(2);
    expect(screen.getByLabelText("4.5 / 5")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /home \(2\)/ })).toBeInTheDocument();
  });

  it("asks again with the category when one is picked in the tree", async () => {
    render(<ShopPage />);
    await userEvent.click(await screen.findByRole("button", { name: /toys \(1\)/ }));
    await waitFor(() => expect(api.mock.calls.some(([url]) => String(url).includes("category=toys"))).toBe(true));
  });

  it("says so when nothing is found", async () => {
    api.mockImplementation(async (url: string) => (url.endsWith("/categories") ? [] : { items: [], next_cursor: null }));
    render(<ShopPage />);
    expect(await screen.findByText("Không tìm thấy sản phẩm.")).toBeInTheDocument();
  });
});
