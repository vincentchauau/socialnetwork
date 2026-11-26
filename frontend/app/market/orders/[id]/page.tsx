"use client";

import Link from "next/link";
import { use, useCallback, useRef, useState } from "react";

import { User, apiFetch } from "@sn/api";
import { API, Order, STATUS_LABELS, errorText, formatDate, formatMoney, newIdempotencyKey } from "../../lib";
import { ErrorLine, Shell, useLoad } from "../../shell";
import Button from "@sn/elements/Button";
import { tr } from "../../i18n";
import Card from "@sn/elements/Card";

function OrderDetail({ id, user }: { id: number; user: User }) {
  const load = useCallback(() => apiFetch<Order>(`${API}/orders/${id}`), [id]);
  const order = useLoad(load, (e) => errorText(e, tr("could_not_load_order")));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const payKey = useRef<string>(newIdempotencyKey());

  async function act(path: string, init: RequestInit) {
    setBusy(true);
    setMessage(null);
    try {
      order.setData(await apiFetch<Order>(`${API}/orders/${id}${path}`, init));
    } catch (error) {
      setMessage(errorText(error, tr("action_failed")));
      order.reload();
    } finally {
      setBusy(false);
    }
  }

  const data = order.data;
  if (order.loading && !data) return <p className="muted">{tr("loading")}</p>;
  if (!data) return <ErrorLine message={order.error ?? tr("order_not_found")} />;
  const isBuyer = data.buyer_username === user.username;
  const canCancel = isBuyer && (data.status === "pending_payment" || data.status === "paid");

  return (
    <>
      <Card stack  style={{ gap: 6 }}>
        <strong>{tr("order")}{data.id}</strong>
        <span aria-live="polite">{tr("status")} {STATUS_LABELS[data.status]}</span>
        <span className="muted">{tr("placed")} {formatDate(data.created_at)}</span>
        <ul style={{ margin: 0, paddingLeft: 20 }}>
          {data.items.map((item) => (
            <li key={item.product_id} style={{ overflowWrap: "anywhere" }}>
              <Link href={`/market/products/${item.product_id}`}>{item.name}</Link> —{" "}
              {formatMoney(item.unit_price_cents, data.currency)} × {item.quantity} ={" "}
              {formatMoney(item.line_total_cents, data.currency)}
            </li>
          ))}
        </ul>
        {data.discount_cents ? (
          <span>{tr("discount_amount", { p1: formatMoney(data.discount_cents, data.currency) })}</span>
        ) : null}
        <strong>{tr("total")} {formatMoney(data.total_cents, data.currency)}</strong>
      </Card>
      <ErrorLine message={message} />
      {isBuyer && data.status === "pending_payment" && (
        <Button
          disabled={busy}
          onClick={() => void act("/pay", { method: "POST", headers: { "Idempotency-Key": payKey.current } })}
        >
          {busy ? tr("working") : tr("pay_p0", { p0: formatMoney(data.total_cents, data.currency) })}
        </Button>
      )}
      {canCancel && (
        <Button variant="secondary"
          className="secondary"
          disabled={busy}
          onClick={() => void act("/status", { method: "PATCH", body: JSON.stringify({ status: "cancelled" }) })}
        >
          {tr("cancel_order")}
        </Button>
      )}
      {isBuyer && data.status === "shipped" && (
        <Button
          disabled={busy}
          onClick={() => void act("/status", { method: "PATCH", body: JSON.stringify({ status: "delivered" }) })}
        >
          {busy ? tr("working") : tr("confirm_delivery")}
        </Button>
      )}
      {isBuyer && data.status === "delivered" && (
        <>
          <p className="muted">Delivered. You can review items from their product pages.</p>
          <Button variant="secondary" disabled={busy} onClick={() => void act("/status", { method: "PATCH", body: JSON.stringify({ status: "return_requested" }) })}>
            {tr("ask_return")}
          </Button>
        </>
      )}
      {isBuyer && data.status === "return_requested" && <p className="muted">{tr("return_waiting")}</p>}
      {!isBuyer && data.status === "return_requested" && (
        <div className="row">
          <Button disabled={busy} onClick={() => void act("/status", { method: "PATCH", body: JSON.stringify({ status: "returned" }) })}>
            {tr("accept_return")}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => void act("/status", { method: "PATCH", body: JSON.stringify({ status: "delivered" }) })}>
            {tr("refuse_return")}
          </Button>
        </div>
      )}
      <Link href="/market/orders">{tr("all_orders")}</Link>
    </>
  );
}

export default function OrderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const orderId = Number(id);
  return (
    <Shell title={tr("order_2")}>
      {(user) =>
        Number.isInteger(orderId) && orderId > 0 ? (
          <OrderDetail id={orderId} user={user} />
        ) : (
          <ErrorLine message={tr("order_not_found")} />
        )
      }
    </Shell>
  );
}
