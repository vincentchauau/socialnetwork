"use client";

import Link from "next/link";
import { use, useCallback, useRef, useState } from "react";

import { User, apiFetch } from "@sn/api";
import { API, Order, STATUS_LABELS, errorText, formatDate, formatMoney, newIdempotencyKey } from "../../lib";
import { ErrorLine, Shell, useLoad } from "../../shell";

function OrderDetail({ id, user }: { id: number; user: User }) {
  const load = useCallback(() => apiFetch<Order>(`${API}/orders/${id}`), [id]);
  const order = useLoad(load, (e) => errorText(e, "Could not load order"));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const payKey = useRef<string>(newIdempotencyKey());

  async function act(path: string, init: RequestInit) {
    setBusy(true);
    setMessage(null);
    try {
      order.setData(await apiFetch<Order>(`${API}/orders/${id}${path}`, init));
    } catch (error) {
      setMessage(errorText(error, "Action failed"));
      order.reload();
    } finally {
      setBusy(false);
    }
  }

  const data = order.data;
  if (order.loading && !data) return <p className="muted">Loading…</p>;
  if (!data) return <ErrorLine message={order.error ?? "Order not found"} />;
  const isBuyer = data.buyer_name === user.username;
  const canCancel = isBuyer && (data.status === "pending_payment" || data.status === "paid");

  return (
    <>
      <div className="card stack" style={{ gap: 6 }}>
        <strong>Order #{data.id}</strong>
        <span aria-live="polite">Status: {STATUS_LABELS[data.status]}</span>
        <span className="muted">Placed {formatDate(data.created_at)}</span>
        <ul style={{ margin: 0, paddingLeft: 20 }}>
          {data.items.map((item) => (
            <li key={item.product_id} style={{ overflowWrap: "anywhere" }}>
              <Link href={`/products/${item.product_id}`}>{item.name}</Link> —{" "}
              {formatMoney(item.unit_price_cents, data.currency)} × {item.quantity} ={" "}
              {formatMoney(item.line_total_cents, data.currency)}
            </li>
          ))}
        </ul>
        <strong>Total: {formatMoney(data.total_cents, data.currency)}</strong>
      </div>
      <ErrorLine message={message} />
      {isBuyer && data.status === "pending_payment" && (
        <button
          disabled={busy}
          onClick={() => void act("/pay", { method: "POST", headers: { "Idempotency-Key": payKey.current } })}
        >
          {busy ? "Working…" : `Pay ${formatMoney(data.total_cents, data.currency)}`}
        </button>
      )}
      {canCancel && (
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void act("/status", { method: "PATCH", body: JSON.stringify({ status: "cancelled" }) })}
        >
          Cancel order
        </button>
      )}
      {isBuyer && data.status === "delivered" && (
        <p className="muted">Delivered. You can review items from their product pages.</p>
      )}
      <Link href="/orders">← All orders</Link>
    </>
  );
}

export default function OrderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const orderId = Number(id);
  return (
    <Shell title="Order">
      {(user) =>
        Number.isInteger(orderId) && orderId > 0 ? (
          <OrderDetail id={orderId} user={user} />
        ) : (
          <ErrorLine message="Order not found" />
        )
      }
    </Shell>
  );
}
