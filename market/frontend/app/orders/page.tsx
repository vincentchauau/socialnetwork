"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { API, Order, Page, STATUS_LABELS, errorText, formatDate, formatMoney } from "../lib";
import { ErrorLine, Shell } from "../shell";

function OrderList() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPage = useCallback(async (cursor: number | null) => {
    setLoading(true);
    setError(null);
    try {
      const query = cursor ? `?cursor=${cursor}` : "";
      const page = await apiFetch<Page<Order>>(`${API}/orders${query}`);
      setOrders((current) => (cursor ? [...current, ...page.items] : page.items));
      setNext(page.next_cursor);
    } catch (failure) {
      setError(errorText(failure, "Could not load orders"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchPage(null);
  }, [fetchPage]);

  return (
    <>
      <ErrorLine message={error} />
      {loading && orders.length === 0 && <p className="muted">Loading…</p>}
      {!loading && !error && orders.length === 0 && (
        <p className="muted">
          You have no orders yet. <Link href="/">Browse products</Link>
        </p>
      )}
      <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {orders.map((order) => (
          <li key={order.id} className="card stack" style={{ gap: 4 }}>
            <Link href={`/orders/${order.id}`}>
              <strong>Order #{order.id}</strong>
            </Link>
            <span>
              {STATUS_LABELS[order.status]} · {formatMoney(order.total_cents, order.currency)}
            </span>
            <span className="muted">{formatDate(order.created_at)}</span>
          </li>
        ))}
      </ul>
      {next !== null && (
        <button className="secondary" disabled={loading} onClick={() => void fetchPage(next)}>
          {loading ? "Loading…" : "Load more"}
        </button>
      )}
    </>
  );
}

export default function OrdersPage() {
  return <Shell title="My orders">{() => <OrderList />}</Shell>;
}
