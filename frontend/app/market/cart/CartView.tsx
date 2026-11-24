"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";

import { apiFetch } from "@sn/api";
import { API, Cart, MAX_CART_QUANTITY, Order, errorText, formatMoney, newIdempotencyKey } from "../lib";
import { notifyCartChanged } from "../cartEvents";
import { ErrorLine, useLoad } from "../shell";
import { confirmDialog } from "@sn/compounds/Dialogs";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import Card from "@sn/elements/Card";
import TextBox from "@sn/elements/TextBox";

export default function CartView({ onOrdered }: { onOrdered?: () => void } = {}) {
  const router = useRouter();
  const load = useCallback(() => apiFetch<Cart>(`${API}/cart`), []);
  const cart = useLoad(load, (e) => errorText(e, tr("could_not_load_your_cart")));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [code, setCode] = useState("");
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
      notifyCartChanged();
      checkoutKey.current = null;
    } catch (error) {
      setMessage(errorText(error, tr("could_not_update_cart")));
    } finally {
      setBusy(false);
    }
  }

  async function emptyCart() {
    if (!(await confirmDialog(tr("empty_the_cart_question")))) return;
    setBusy(true);
    setMessage(null);
    try {
      cart.setData(await apiFetch<Cart>(`${API}/cart`, { method: "DELETE" }));
      notifyCartChanged();
      checkoutKey.current = null;
    } catch (error) {
      setMessage(errorText(error, tr("could_not_update_cart")));
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
        ...(code.trim() ? { body: JSON.stringify({ code: code.trim() }) } : {}),
      });
      if (onOrdered) {
        notifyCartChanged();
        onOrdered(); // in the market view the order waits in the Pay tab
      } else router.push(`/market/orders/${order.id}`);
    } catch (error) {
      checkoutKey.current = null;
      setMessage(errorText(error, tr("checkout_failed")));
      cart.reload();
      setBusy(false);
    }
  }

  const data = cart.data;
  if (cart.loading && !data) return <p className="muted">{tr("loading")}</p>;
  if (!data) return <ErrorLine message={cart.error} />;
  if (data.items.length === 0) {
    return (
      <p className="muted">
        {tr("your_cart_is_empty")} <Link href="/market">{tr("browse_products")}</Link>
      </p>
    );
  }

  return (
    <>
      <ErrorLine message={cart.error} />
      <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {data.items.map((line) => (
          <Card stack as="li" key={line.product_id}  style={{ gap: 6 }}>
            {line.image_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={line.image_url} alt="" loading="lazy" style={{ width: 96, height: 72, objectFit: "cover", borderRadius: 6 }} />
            )}
            <Link href={`/market/products/${line.product_id}`} style={{ overflowWrap: "anywhere" }}>
              <strong>{line.name}</strong>
            </Link>
            <span>
              {formatMoney(line.unit_price_cents, data.currency)} × {line.quantity} ={" "}
              <strong>{formatMoney(line.line_total_cents, data.currency)}</strong>
            </span>
            <div className="row" style={{ flexWrap: "wrap" }}>
              <Button variant="secondary"
                className="secondary"
                aria-label={tr("decrease_quantity_of_p0", { p0: line.name })}
                disabled={busy}
                onClick={() => void changeQuantity(line.product_id, line.quantity - 1)}
              >
                −
              </Button>
              <span aria-live="polite" style={{ alignSelf: "center" }}>
                {line.quantity}
              </span>
              <Button variant="secondary"
                className="secondary"
                aria-label={tr("increase_quantity_of_p0", { p0: line.name })}
                disabled={busy || line.quantity >= Math.min(line.stock, MAX_CART_QUANTITY)}
                onClick={() => void changeQuantity(line.product_id, line.quantity + 1)}
              >
                +
              </Button>
              <Button variant="secondary" className="secondary" disabled={busy} onClick={() => void changeQuantity(line.product_id, 0)}>
                {tr("remove")}
              </Button>
            </div>
          </Card>
        ))}
      </ul>
      <p style={{ margin: 0 }}>
        Total ({data.item_count} items): <strong>{formatMoney(data.total_cents, data.currency)}</strong>
      </p>
      <label className="row" style={{ alignItems: "center", gap: 8 }}>
        {tr("discount_code")}
        <TextBox value={code} maxLength={32} disabled={busy} onChange={(event) => { setCode(event.target.value); checkoutKey.current = null; }} />
      </label>
      <ErrorLine message={message} />
      <div className="row">
        <Button disabled={busy} onClick={() => void placeOrder()}>
          {busy ? tr("working") : tr("checkout")}
        </Button>
        <Button variant="secondary" disabled={busy} onClick={() => void emptyCart()}>
          {tr("clear_cart")}
        </Button>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        {tr("you_pay_on_the_next_step")}
      </p>
    </>
  );
}

