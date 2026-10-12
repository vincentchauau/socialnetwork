"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";

import { apiFetch } from "@sn/api";
import { API, Cart, MAX_CART_QUANTITY, Order, errorText, formatMoney, newIdempotencyKey } from "../lib";
import { ErrorLine, Shell, useLoad } from "../shell";

function CartView() {
  const router = useRouter();
  const load = useCallback(() => apiFetch<Cart>(`${API}/cart`), []);
  const cart = useLoad(load, (e) => errorText(e, "Could not load your cart"));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  // One key per checkout attempt: a double click or retry cannot create two orders.
  const checkoutKey = useRef<string | null>(null);

  async function changeQuantity(productId: number, quantity: number) {
    setBusy(true);
    setMessage(null);
    try {
      const next = await apiFetch<Cart>(`${API}/cart/items/${productId}`, {
        method: "PUT",
        body: JSON.stringify({ quantity }),
      });
      cart.setData(next);
      checkoutKey.current = null;
    } catch (error) {
      setMessage(errorText(error, "Could not update cart"));
    } finally {
      setBusy(false);
    }
  }

  async function placeOrder() {
    setBusy(true);
    setMessage(null);
    checkoutKey.current ??= newIdempotencyKey();
    try {
      const order = await apiFetch<Order>(`${API}/orders`, {
        method: "POST",
        headers: { "Idempotency-Key": checkoutKey.current },
      });
      router.push(`/orders/${order.id}`);
    } catch (error) {
      checkoutKey.current = null;
      setMessage(errorText(error, "Checkout failed"));
      cart.reload();
      setBusy(false);
    }
  }

  const data = cart.data;
  if (cart.loading && !data) return <p className="muted">Loading…</p>;
  if (!data) return <ErrorLine message={cart.error} />;
  if (data.items.length === 0) {
    return (
      <p className="muted">
        Your cart is empty. <Link href="/">Browse products</Link>
      </p>
    );
  }

  return (
    <>
      <ErrorLine message={cart.error} />
      <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {data.items.map((line) => (
          <li key={line.product_id} className="card stack" style={{ gap: 6 }}>
            <Link href={`/products/${line.product_id}`} style={{ overflowWrap: "anywhere" }}>
              <strong>{line.name}</strong>
            </Link>
            <span>
              {formatMoney(line.unit_price_cents, data.currency)} × {line.quantity} ={" "}
              <strong>{formatMoney(line.line_total_cents, data.currency)}</strong>
            </span>
            <div className="row" style={{ flexWrap: "wrap" }}>
              <button
                className="secondary"
                aria-label={`Decrease quantity of ${line.name}`}
                disabled={busy}
                onClick={() => void changeQuantity(line.product_id, line.quantity - 1)}
              >
                −
              </button>
              <span aria-live="polite" style={{ alignSelf: "center" }}>
                {line.quantity}
              </span>
              <button
                className="secondary"
                aria-label={`Increase quantity of ${line.name}`}
                disabled={busy || line.quantity >= Math.min(line.stock, MAX_CART_QUANTITY)}
                onClick={() => void changeQuantity(line.product_id, line.quantity + 1)}
              >
                +
              </button>
              <button className="secondary" disabled={busy} onClick={() => void changeQuantity(line.product_id, 0)}>
                Remove
              </button>
            </div>
          </li>
        ))}
      </ul>
      <p style={{ margin: 0 }}>
        Total ({data.item_count} items): <strong>{formatMoney(data.total_cents, data.currency)}</strong>
      </p>
      <ErrorLine message={message} />
      <button disabled={busy} onClick={() => void placeOrder()}>
        {busy ? "Working…" : "Checkout"}
      </button>
      <p className="muted" style={{ margin: 0 }}>
        You pay on the next step. No card details are collected in this demo.
      </p>
    </>
  );
}

export default function CartPage() {
  return <Shell title="Your cart">{() => <CartView />}</Shell>;
}
