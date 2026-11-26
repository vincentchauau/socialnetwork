"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { apiFetch } from "@sn/api";
import Button from "@sn/elements/Button";
import Card from "@sn/elements/Card";
import { usePagedList } from "@sn/lib/hooks";
import { API, Order, Page, errorText, formatDate, formatMoney, newIdempotencyKey } from "../lib";
import { ErrorLine } from "../shell";
import { tr } from "../i18n";

/** The orders that wait for payment, each with Pay and Cancel: a paid or cancelled order leaves the list. */
export default function PayList() {
  const [done, setDone] = useState<ReadonlySet<number>>(new Set());
  const [busy, setBusy] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const keys = useRef(new Map<number, string>()); // one key for each order: a double click cannot charge twice
  const list = usePagedList<Order, number>(
    (cursor) => apiFetch<Page<Order>>(`${API}/orders${cursor ? `?cursor=${cursor}` : ""}`),
    [],
    (failure) => errorText(failure, tr("could_not_load_orders")),
  );
  const waiting = list.items.filter((order) => order.status === "pending_payment" && !done.has(order.id));

  async function act(order: Order, path: string, init: RequestInit) {
    setBusy(order.id);
    setMessage(null);
    try {
      await apiFetch<Order>(`${API}/orders/${order.id}${path}`, init);
      setDone((current) => new Set([...current, order.id]));
    } catch (failure) {
      setMessage(errorText(failure, tr("action_failed")));
    } finally {
      setBusy(null);
    }
  }

  function pay(order: Order) {
    if (!keys.current.has(order.id)) keys.current.set(order.id, newIdempotencyKey());
    void act(order, "/pay", { method: "POST", headers: { "Idempotency-Key": keys.current.get(order.id) as string } });
  }

  return (
    <div className="stack">
      <ErrorLine message={list.error ?? message} />
      {list.loading && waiting.length === 0 && <p className="muted">{tr("loading")}</p>}
      {!list.loading && !list.error && waiting.length === 0 && <p className="muted">{tr("nothing_to_pay")}</p>}
      <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {waiting.map((order) => (
          <Card stack as="li" key={order.id} style={{ gap: 6 }}>
            <Link href={`/market/orders/${order.id}`}><strong>{tr("order")}{order.id}</strong></Link>
            <span className="muted" style={{ overflowWrap: "anywhere" }}>{order.items.map((item) => `${item.name} × ${item.quantity}`).join(", ")}</span>
            <span className="muted">{formatDate(order.created_at)}</span>
            {order.discount_cents ? <span>{tr("discount_amount", { p1: formatMoney(order.discount_cents, order.currency) })}</span> : null}
            <div className="row">
              <Button disabled={busy !== null} onClick={() => pay(order)}>
                {busy === order.id ? tr("working") : tr("pay_p0", { p0: formatMoney(order.total_cents, order.currency) })}
              </Button>
              <Button variant="secondary" disabled={busy !== null} onClick={() => void act(order, "/status", { method: "PATCH", body: JSON.stringify({ status: "cancelled" }) })}>
                {tr("cancel_order")}
              </Button>
            </div>
          </Card>
        ))}
      </ul>
      {list.hasMore && <Button variant="secondary" disabled={list.loadingMore} onClick={list.loadMore}>{list.loadingMore ? tr("loading") : tr("load_more")}</Button>}
    </div>
  );
}
