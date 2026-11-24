"use client";

import Link from "next/link";
import { FormEvent, useCallback, useState } from "react";

import { apiFetch } from "@sn/api";
import { notifyRecordsChanged } from "@sn/lib/recordsChanged";
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
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import { confirmDialog } from "@sn/compounds/Dialogs";
import TextBox from "@sn/elements/TextBox";
import Card from "@sn/elements/Card";

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
  paid: { target: "shipped", get label() { return tr("mark_shipped"); } },
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
    if (cents === null) return setError(tr("enter_a_price_like_12_50"));
    if (!Number.isInteger(stock) || stock < 0) return setError(tr("stock_must_be_a_whole_number"));
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
      setError(errorText(failure, tr("could_not_save_product")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={submit}>
      <label className="stack" style={{ gap: 4 }}>
        {tr("name")}
        <TextBox required maxLength={120} {...bind("name")} />
      </label>
      <label className="stack" style={{ gap: 4 }}>
        {tr("description")}
        <TextBox multiline rows={3} maxLength={4000} style={fieldStyle} {...bind("description")} />
      </label>
      <div className="row" style={{ flexWrap: "wrap" }}>
        <label className="stack" style={{ gap: 4, flex: 1, minWidth: 120 }}>
          {tr("price_usd")}
          <TextBox required inputMode="decimal" {...bind("price")} />
        </label>
        <label className="stack" style={{ gap: 4, flex: 1, minWidth: 120 }}>
          {tr("stock")}
          <TextBox required inputMode="numeric" {...bind("stock")} />
        </label>
      </div>
      <label className="stack" style={{ gap: 4 }}>
        {tr("image_url_https_optional")}
        <TextBox type="url" maxLength={500} {...bind("imageUrl")} />
      </label>
      <label className="stack" style={{ gap: 4 }}>
        {tr("category")}
        <TextBox maxLength={40} {...bind("category")} />
      </label>
      <ErrorLine message={error} />
      <div className="row">
        <Button disabled={busy}>{busy ? tr("saving") : submitLabel}</Button>
        {onCancel && (
          <Button variant="secondary" type="button" className="secondary" onClick={onCancel}>
            {tr("cancel")}
          </Button>
        )}
      </div>
    </form>
  );
}

function MyProducts() {
  const load = useCallback(() => apiFetch<Page<Product>>(`${API}/me/products?limit=50`), []);
  const mine = useLoad(load, (e) => errorText(e, tr("could_not_load_your_products")));
  const [editing, setEditing] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function remove(product: Product) {
    if (!(await confirmDialog(tr("delete_p0", { p0: product.name })))) return;
    setMessage(null);
    try {
      await apiFetch(`${API}/products/${product.id}`, { method: "DELETE" });
      mine.reload();
    } catch (error) {
      setMessage(errorText(error, tr("could_not_delete_product")));
    }
  }

  return (
    <section className="stack" aria-labelledby="mine-heading">
      <h2 id="mine-heading" style={{ margin: 0, fontSize: "1.2rem" }}>
        {tr("my_products")}
      </h2>
      <Card as="details">
        <summary>{tr("new_product")}</summary>
        <ProductForm
          initial={EMPTY_DRAFT}
          submitLabel={tr("create_product")}
          onSubmit={async (body) => {
            await apiFetch(`${API}/products`, { method: "POST", body: JSON.stringify(body) });
            notifyRecordsChanged("market_products");
            mine.reload();
          }}
        />
      </Card>
      <ErrorLine message={mine.error ?? message} />
      {mine.loading && !mine.data && <p className="muted">{tr("loading")}</p>}
      {mine.data && mine.data.items.length === 0 && <p className="muted">{tr("you_have_not_listed_anything_yet")}</p>}
      <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {mine.data?.items.map((product) => (
          <Card stack as="li" key={product.id}  style={{ gap: 6 }}>
            {editing === product.id ? (
              <ProductForm
                initial={toDraft(product)}
                submitLabel={tr("save")}
                onCancel={() => setEditing(null)}
                onSubmit={async (body) => {
                  await apiFetch(`${API}/products/${product.id}`, { method: "PUT", body: JSON.stringify(body) });
                  setEditing(null);
                  mine.reload();
                }}
              />
            ) : (
              <>
                <Link href={`/market/products/${product.id}`} style={{ overflowWrap: "anywhere" }}>
                  <strong>{product.name}</strong>
                </Link>
                <span>
                  {formatMoney(product.price_cents, product.currency)} · {product.stock} {tr("in_stock")}
                </span>
                <div className="row">
                  <Button variant="secondary" className="secondary" onClick={() => setEditing(product.id)}>
                    {tr("edit")}
                  </Button>
                  <Button variant="secondary" className="secondary" onClick={() => void remove(product)}>
                    {tr("delete")}
                  </Button>
                </div>
              </>
            )}
          </Card>
        ))}
      </ul>
    </section>
  );
}

function Sales() {
  const load = useCallback(() => apiFetch<Page<Order>>(`${API}/sales?limit=50`), []);
  const sales = useLoad(load, (e) => errorText(e, tr("could_not_load_sales")));
  const [message, setMessage] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  async function advance(order: Order, target: OrderStatus) {
    setBusyId(order.id);
    setMessage(null);
    try {
      await apiFetch(`${API}/orders/${order.id}/status`, { method: "PATCH", body: JSON.stringify({ status: target }) });
      sales.reload();
    } catch (error) {
      setMessage(errorText(error, tr("could_not_update_status")));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="stack" aria-labelledby="sales-heading">
      <h2 id="sales-heading" style={{ margin: 0, fontSize: "1.2rem" }}>
        {tr("sales")}
      </h2>
      <ErrorLine message={sales.error ?? message} />
      {sales.loading && !sales.data && <p className="muted">{tr("loading")}</p>}
      {sales.data && sales.data.items.length === 0 && <p className="muted">{tr("no_sales_yet")}</p>}
      <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {sales.data?.items.map((order) => {
          const next = SELLER_NEXT[order.status];
          return (
            <Card stack as="li" key={order.id}  style={{ gap: 4 }}>
              <strong>
                {tr("order")}{order.id} · {STATUS_LABELS[order.status]}
              </strong>
              <span className="muted" style={{ overflowWrap: "anywhere" }}>
                {order.buyer_username} · {formatDate(order.created_at)}
              </span>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {order.items.map((item) => (
                  <li key={item.product_id} style={{ overflowWrap: "anywhere" }}>
                    {item.name} × {item.quantity} = {formatMoney(item.line_total_cents, order.currency)}
                  </li>
                ))}
              </ul>
              <span>{tr("your_total")} {formatMoney(order.total_cents, order.currency)}</span>
              {next && (
                <Button disabled={busyId === order.id} onClick={() => void advance(order, next.target)}>
                  {next.label}
                </Button>
              )}
            </Card>
          );
        })}
      </ul>
    </section>
  );
}

export default function SellPage() {
  return (
    <Shell title={tr("seller_dashboard")}>
      {() => (
        <>
          <MyProducts />
          <Sales />
        </>
      )}
    </Shell>
  );
}
