"use client";

import SavedProducts from "./SavedProducts";

import { useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import GalleryView, { type GalleryConfig } from "@sn/compounds/GalleryView";
import TextBox from "@sn/elements/TextBox";
import { TabPanel } from "@sn/compounds/SplitPanel";

import CartView from "./cart/CartView";
import { onCartChanged } from "./cartEvents";
import { API, type Cart } from "./lib";
import { tr } from "./i18n";
import OrderList from "./orders/OrderList";
import PayList from "./orders/PayList";
import Shop from "./Shop";

/** The products the person sells: their own, with a card for each (rename, edit, delete); a new one is made with the seller form. */
const MINE: GalleryConfig = {
  title: "name",
  friendly: true,
  renameColumn: "name",
  image: "image_url",
  body: "description",
  badge: "category",
  meta: ["price_cents", "stock", "is_active"],
  quietFlags: true,
  sort: [{ column: "-created_at", label: "Mới nhất / Newest" }, { column: "created_at", label: "Cũ nhất / Oldest" }],
  searchPlaceholder: "Tìm sản phẩm của tôi / Search my products",
  addHref: "/market/sell",
  addLabel: "Đăng bán / Sell a product",
  emptyText: "Bạn chưa đăng bán sản phẩm nào / You are not selling anything yet",
};

/** How many things are in the cart of the person, asked for again whenever the cart changes. */
function useCartCount(): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const ask = () => {
      apiFetch<Cart>(`${API}/cart`).then(
        (cart) => !cancelled && setCount(cart.items.reduce((sum, line) => sum + line.quantity, 0)),
        () => undefined, // not worth an error: the tab simply shows no number
      );
    };
    ask();
    const stop = onCartChanged(ask);
    return () => {
      cancelled = true;
      stop();
    };
  }, []);
  return count;
}

/** The market the way a shop shows itself: a search box over everything, the products to buy first, then the cart, the orders and what the person sells. No props, no page chrome. */
export default function MarketLibrary() {
  const [tab, setTab] = useState("shop");
  const [typed, setTyped] = useState("");
  const [words, setWords] = useState("");
  const cart = useCartCount();
  return (
    <div className="stack">
      <form
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          setWords(typed.trim());
          setTab("shop");
        }}
        style={{ display: "flex", gap: 8 }}
      >
        <TextBox type="search" aria-label={tr("search_products")} placeholder={tr("search_products")} value={typed} maxLength={100} onChange={(event) => setTyped(event.target.value)} style={{ flex: 1, minWidth: 0 }} />
      </form>
      <TabPanel
        aria-label={tr("market")}
        keepMounted={false}
        activeKey={tab}
        onChange={setTab}
        data={[
          { key: "mine", label: tr("tab_crud_products") },
          { key: "saved", label: tr("tab_saved_products") },
          { key: "shop", label: tr("tab_create_order") },
          { key: "cart", label: cart > 0 ? `${tr("tab_update_order")} (${cart})` : tr("tab_update_order") },
          { key: "pay", label: tr("tab_pay_order") },
          { key: "orders", label: tr("tab_my_orders") },
        ]}
        panels={{
          shop: <Shop key={words} initialQuery={words} />,
          cart: <CartView onOrdered={() => setTab("pay")} />,
          pay: <PayList key={tab === "pay" ? "open" : "closed"} />,
          orders: <OrderList />,
          saved: <SavedProducts />,
          mine: <GalleryView api={`${API}/records`} table="market_products" config={MINE} />,
        }}
      />
    </div>
  );
}
