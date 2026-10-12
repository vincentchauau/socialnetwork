"use client";

import Link from "next/link";
import { FormEvent, useCallback, useState } from "react";

import { apiFetch } from "@sn/api";
import {
  API,
  Order,
  OrderStatus,
  Page,
  Product,
  STATUS_LABELS,
  errorText,
  formatDate,
  formatMoney,
  parsePriceToCents,
} from "../lib";
import { ErrorLine, Shell, useLoad } from "../shell";

interface Draft {
  name: string;
  description: string;
  price: string;
  stock: string;
  imageUrl: string;
  category: string;
}

const EMPTY_DRAFT: Draft = { name: "", description: "", price: "", stock: "1", imageUrl: "", category: "other" };
const SELLER_NEXT: Partial<Record<OrderStatus, { target: OrderStatus; label: string }>> = {
  // Sellers only ship; the buyer confirms delivery. A multi-seller order shares one status.
  paid: { target: "shipped", label: "Mark shipped" },
};
const fieldStyle = { font: "inherit", padding: 8 } as const;

function toDraft(product: Product): Draft {
  return {
    name: product.name,
    description: product.description,
    price: (product.price_cents / 100).toFixed(2),
    stock: String(product.stock),
    imageUrl: product.image_url ?? "",
    category: product.category,
  };
}

function ProductForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial: Draft;
  submitLabel: string;
  onSubmit: (body: Record<string, unknown>) => Promise<void>;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bind = (key: keyof Draft) => ({
    value: draft[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setDraft({ ...draft, [key]: event.target.value }),
  });

  async function submit(event: FormEvent) {
    event.preventDefault();
    const cents = parsePriceToCents(draft.price);
    const stock = Number(draft.stock);
    if (cents === null) return setError("Enter a price like 12.50");
    if (!Number.isInteger(stock) || stock < 0) return setError("Stock must be a whole number, 0 or more");
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        name: draft.name,
        description: draft.description,
        price_cents: cents,
        stock,
        image_url: draft.imageUrl.trim() || null,
        category: draft.category || "other",
      });
      if (!onCancel) setDraft(EMPTY_DRAFT);
    } catch (failure) {
      setError(errorText(failure, "Could not save product"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={submit}>
      <label className="stack" style={{ gap: 4 }}>
        Name
        <input required maxLength={120} {...bind("name")} />
      </label>
      <label className="stack" style={{ gap: 4 }}>
        Description
        <textarea rows={3} maxLength={4000} style={fieldStyle} {...bind("description")} />
      </label>
      <div className="row" style={{ flexWrap: "wrap" }}>
        <label className="stack" style={{ gap: 4, flex: 1, minWidth: 120 }}>
          Price (USD)
          <input required inputMode="decimal" {...bind("price")} />
        </label>
        <label className="stack" style={{ gap: 4, flex: 1, minWidth: 120 }}>
          Stock
          <input required inputMode="numeric" {...bind("stock")} />
        </label>
      </div>
      <label className="stack" style={{ gap: 4 }}>
        Image URL (https, optional)
        <input type="url" maxLength={500} {...bind("imageUrl")} />
      </label>
      <label className="stack" style={{ gap: 4 }}>
        Category
        <input maxLength={40} {...bind("category")} />
      </label>
      <ErrorLine message={error} />
      <div className="row">
        <button disabled={busy}>{busy ? "Saving…" : submitLabel}</button>
        {onCancel && (
          <button type="button" className="secondary" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

function MyProducts() {
  const load = useCallback(() => apiFetch<Page<Product>>(`${API}/me/products?limit=50`), []);
  const mine = useLoad(load, (e) => errorText(e, "Could not load your products"));
  const [editing, setEditing] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function remove(product: Product) {
    if (!window.confirm(`Delete "${product.name}"?`)) return;
    setMessage(null);
    try {
      await apiFetch(`${API}/products/${product.id}`, { method: "DELETE" });
      mine.reload();
    } catch (error) {
      setMessage(errorText(error, "Could not delete product"));
    }
  }

  return (
    <section className="stack" aria-labelledby="mine-heading">
      <h2 id="mine-heading" style={{ margin: 0, fontSize: "1.2rem" }}>
        My products
      </h2>
      <details className="card">
        <summary>New product</summary>
        <ProductForm
          initial={EMPTY_DRAFT}
          submitLabel="Create product"
          onSubmit={async (body) => {
            await apiFetch(`${API}/products`, { method: "POST", body: JSON.stringify(body) });
            mine.reload();
          }}
        />
      </details>
      <ErrorLine message={mine.error ?? message} />
      {mine.loading && !mine.data && <p className="muted">Loading…</p>}
      {mine.data && mine.data.items.length === 0 && <p className="muted">You have not listed anything yet.</p>}
      <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {mine.data?.items.map((product) => (
          <li key={product.id} className="card stack" style={{ gap: 6 }}>
            {editing === product.id ? (
              <ProductForm
                initial={toDraft(product)}
                submitLabel="Save"
                onCancel={() => setEditing(null)}
                onSubmit={async (body) => {
                  await apiFetch(`${API}/products/${product.id}`, { method: "PUT", body: JSON.stringify(body) });
                  setEditing(null);
                  mine.reload();
                }}
              />
            ) : (
              <>
                <Link href={`/products/${product.id}`} style={{ overflowWrap: "anywhere" }}>
                  <strong>{product.name}</strong>
                </Link>
                <span>
                  {formatMoney(product.price_cents, product.currency)} · {product.stock} in stock
                </span>
                <div className="row">
                  <button className="secondary" onClick={() => setEditing(product.id)}>
                    Edit
                  </button>
                  <button className="secondary" onClick={() => void remove(product)}>
                    Delete
                  </button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Sales() {
  const load = useCallback(() => apiFetch<Page<Order>>(`${API}/sales?limit=50`), []);
  const sales = useLoad(load, (e) => errorText(e, "Could not load sales"));
  const [message, setMessage] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  async function advance(order: Order, target: OrderStatus) {
    setBusyId(order.id);
    setMessage(null);
    try {
      await apiFetch(`${API}/orders/${order.id}/status`, { method: "PATCH", body: JSON.stringify({ status: target }) });
      sales.reload();
    } catch (error) {
      setMessage(errorText(error, "Could not update status"));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="stack" aria-labelledby="sales-heading">
      <h2 id="sales-heading" style={{ margin: 0, fontSize: "1.2rem" }}>
        Sales
      </h2>
      <ErrorLine message={sales.error ?? message} />
      {sales.loading && !sales.data && <p className="muted">Loading…</p>}
      {sales.data && sales.data.items.length === 0 && <p className="muted">No sales yet.</p>}
      <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {sales.data?.items.map((order) => {
          const next = SELLER_NEXT[order.status];
          return (
            <li key={order.id} className="card stack" style={{ gap: 4 }}>
              <strong>
                Order #{order.id} · {STATUS_LABELS[order.status]}
              </strong>
              <span className="muted" style={{ overflowWrap: "anywhere" }}>
                {order.buyer_name} · {formatDate(order.created_at)}
              </span>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {order.items.map((item) => (
                  <li key={item.product_id} style={{ overflowWrap: "anywhere" }}>
                    {item.name} × {item.quantity} = {formatMoney(item.line_total_cents, order.currency)}
                  </li>
                ))}
              </ul>
              <span>Your total: {formatMoney(order.total_cents, order.currency)}</span>
              {next && (
                <button disabled={busyId === order.id} onClick={() => void advance(order, next.target)}>
                  {next.label}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default function SellPage() {
  return (
    <Shell title="Seller dashboard">
      {() => (
        <>
          <MyProducts />
          <Sales />
        </>
      )}
    </Shell>
  );
}
