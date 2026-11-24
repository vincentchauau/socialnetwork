"use client";

import Link from "next/link";
import { useState } from "react";

import { apiFetch } from "@sn/api";
import { confirmDialog } from "@sn/compounds/Dialogs";
import { GridView } from "@sn/compounds/GalleryView";
import Button from "@sn/elements/Button";
import { usePagedList } from "@sn/lib/hooks";
import { API, Order, Page, STATUS_LABELS, errorText, formatDate, formatMoney } from "../lib";
import { ErrorLine } from "../shell";
import { tr } from "../i18n";
import Card from "@sn/elements/Card";

function OrderCard({ order, onDelete }: { order: Order; onDelete: (order: Order) => void }) {
  return (
    <Card stack as="article" style={{ gap: 4, height: "100%", boxSizing: "border-box" }}>
      <Link href={`/market/orders/${order.id}`}>
        <strong>{tr("order")}{order.id}</strong>
      </Link>
      <span>
        {STATUS_LABELS[order.status]} · {formatMoney(order.total_cents, order.currency)}
      </span>
      <span className="muted" style={{ overflowWrap: "anywhere" }}>{order.items.map((item) => `${item.name} × ${item.quantity}`).join(", ")}</span>
      <span className="muted">{formatDate(order.created_at)}</span>
      {order.status === "cancelled" && (
        <div className="row">
          <Button variant="secondary" size="sm" onClick={() => onDelete(order)}>{tr("delete_order")}</Button>
        </div>
      )}
    </Card>
  );
}

export default function OrderList() {
  const [gone, setGone] = useState<ReadonlySet<number>>(new Set());
  const [message, setMessage] = useState<string | null>(null);
  const list = usePagedList<Order, number>(
    (cursor) => apiFetch<Page<Order>>(`${API}/orders${cursor ? `?cursor=${cursor}` : ""}`),
    [],
    (failure) => errorText(failure, tr("could_not_load_orders")),
  );
  const orders = list.items.filter((order) => !gone.has(order.id));

  async function remove(order: Order) {
    if (!(await confirmDialog(tr("delete_this_order_question", { p0: order.id })))) return;
    setMessage(null);
    try {
      await apiFetch(`${API}/orders/${order.id}`, { method: "DELETE" });
      setGone((current) => new Set([...current, order.id]));
    } catch (failure) {
      setMessage(errorText(failure, tr("action_failed")));
    }
  }

  return (
    <>
      <ErrorLine message={list.error ?? message} />
      {list.loading && orders.length === 0 && <p className="muted">{tr("loading")}</p>}
      {!list.loading && !list.error && orders.length === 0 && (
        <p className="muted">
          {tr("you_have_no_orders_yet")} <Link href="/market">{tr("browse_products")}</Link>
        </p>
      )}
      <GridView items={orders} itemKey={(order) => order.id} renderItem={(order) => <OrderCard order={order} onDelete={(o) => void remove(o)} />} label={tr("my_orders")} minColumnWidth={260} gap={12} />
      {list.hasMore && (
        <Button variant="secondary" disabled={list.loadingMore} onClick={list.loadMore}>
          {list.loadingMore ? tr("loading") : tr("load_more")}
        </Button>
      )}
    </>
  );
}

