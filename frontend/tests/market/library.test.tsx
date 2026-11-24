import { apiFetch } from "@sn/api";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MarketLibrary from "../../app/market/MarketLibrary";

vi.mock("@sn/lib/useSession", () => ({ useSession: () => ({ status: "signed-in", user: { id: 1, username: "a", group: "user" } }) }));
vi.mock("next/navigation", () => ({ usePathname: () => "/market" }));
vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn() }));

const api = vi.mocked(apiFetch);
const product = (id: number, name: string) => ({ id, seller_id: 2, seller_username: "bob", name, description: "", price_cents: 1250, currency: "USD", stock: 3, image_url: null, category: "home", rating_average: null, review_count: 0, created_at: "2025-01-01T00:00:00Z" });
const col = (name: string) => ({ name, type: "string", nullable: false, readonly: false, secret: false });

beforeEach(() => {
  api.mockReset();
  api.mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method === "PUT") return {};
    if (url.includes("/orders")) return { items: [], next_cursor: null };
    if (url.endsWith("/categories")) return [{ name: "home", count: 1 }];
    if (url.endsWith("/cart")) return { items: [{ product_id: 1, quantity: 2 }, { product_id: 3, quantity: 1 }], currency: "USD", total_cents: 0 };
    if (url.endsWith("/tables")) return [{ name: "market_products", label: "products", pk: ["id"], columns: [{ ...col("id"), type: "int", readonly: true }, col("name")], writable: true }];
    if (url.includes("/records/market_products")) return { total: 1, rows: [{ id: 9, name: "Mine to sell" }] };
    if (url.includes("/groups")) return { values: [] };
    return { items: [product(1, "Lamp")], next_cursor: null };
  });
});

describe("the market as a shop", () => {
  it("opens on the products to buy, and puts one in the cart with one press", async () => {
    render(<MarketLibrary />);
    expect(await screen.findByRole("link", { name: "Lamp" })).toHaveAttribute("href", "/market/products/1");
    await userEvent.click(screen.getByRole("button", { name: /Thêm vào giỏ|Add to cart/ }));
    await waitFor(() => expect(api.mock.calls.some(([url, init]) => String(url).endsWith("/cart/items/1") && (init as RequestInit | undefined)?.method === "PUT")).toBe(true));
    expect(await screen.findByRole("button", { name: /✓/ })).toBeInTheDocument();
  });

  it("has a tab for the cart, the orders and what the person sells", async () => {
    render(<MarketLibrary />);
    expect(await screen.findByRole("link", { name: /Tạo đơn|Create order/ })).toHaveAttribute("aria-current", "page");
    await userEvent.click(screen.getByRole("link", { name: /Quản lý sản phẩm|CRUD products/ }));
    expect(await screen.findByRole("article", { name: "Mine to sell" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Sell a product|Đăng bán/ })).toHaveAttribute("href", "/market/sell");
  });

  it("shows how many things are in the cart on its tab", async () => {
    render(<MarketLibrary />);
    expect(await screen.findByRole("link", { name: /\(3\)/ })).toBeInTheDocument();
  });

  it("searches the products from a box over the tabs, wherever the person is", async () => {
    render(<MarketLibrary />);
    await userEvent.click(await screen.findByRole("link", { name: /Đơn hàng của tôi|My orders/ }));
    await userEvent.type(screen.getByRole("searchbox", { name: /sản phẩm|products/i }), "lamp");
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByRole("link", { name: /Tạo đơn|Create order/ })).toHaveAttribute("aria-current", "page");
    await waitFor(() => expect(api.mock.calls.some(([url]) => String(url).includes("q=lamp"))).toBe(true));
  });
});
