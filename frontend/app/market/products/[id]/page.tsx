"use client";

import { FormEvent, use, useCallback, useEffect, useState } from "react";

import Comments from "@sn/compounds/Comments";

import { User, apiFetch } from "@sn/api";
import { API, MAX_CART_QUANTITY, Product, errorText, formatMoney } from "../../lib";
import { ErrorLine, Shell, useLoad } from "../../shell";
import Button from "@sn/elements/Button";
import { tr } from "../../i18n";
import TextBox from "@sn/elements/TextBox";
import Card from "@sn/elements/Card";

function ProductDetail({ id, user }: { id: number; user: User }) {
  const load = useCallback(() => apiFetch<Product>(`${API}/products/${id}`), [id]);
  const product = useLoad(load, (e) => errorText(e, tr("could_not_load_product")));
  const [quantity, setQuantity] = useState("1");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  async function addToCart(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      await apiFetch(`${API}/cart/items/${id}`, {
        method: "PUT",
        body: JSON.stringify({ quantity: Number(quantity) }),
      });
      setFailed(false);
      setMessage(tr("added_to_your_cart"));
    } catch (error) {
      setFailed(true);
      setMessage(errorText(error, tr("could_not_update_cart")));
    } finally {
      setBusy(false);
    }
  }

  const item = product.data;
  if (product.loading && !item) return <p className="muted">{tr("loading")}</p>;
  if (!item) return <ErrorLine message={product.error ?? tr("product_not_found")} />;
  const own = item.seller_id === user.id;

  return (
    <>
      <Card style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "flex-start", width: "100%", boxSizing: "border-box" }}>
        {item.image_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={item.image_url} alt="" style={{ flex: "1 1 260px", maxWidth: "100%", maxHeight: 360, objectFit: "contain" }} />
        )}
        <div className="stack" style={{ flex: "2 1 300px", minWidth: 0 }}>
        <h2 style={{ margin: 0, overflowWrap: "anywhere" }}>{item.name}</h2>
        <strong>{formatMoney(item.price_cents, item.currency)}</strong>
        <span className="muted">
          {tr("by")} {item.seller_username} · {item.category} ·{" "}
          {item.rating_average === null
            ? tr("no_reviews_yet")
            : `★ ${item.rating_average} (${item.review_count})`}
        </span>
        <p style={{ margin: 0, overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}>{item.description}</p>
        <span className="muted">{item.stock > 0 ? tr("p0_in_stock", { p0: item.stock }) : tr("sold_out")}</span>
        {own ? (
          <p className="muted">{tr("this_is_your_product")}</p>
        ) : (
          <form className="row" onSubmit={addToCart}>
            <TextBox
              type="number"
              aria-label={tr("quantity")}
              min={1}
              max={MAX_CART_QUANTITY}
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              style={{ maxWidth: 90, flex: "none" }}
            />
            <Button disabled={busy || item.stock === 0}>{tr("add_to_cart")}</Button>
          </form>
        )}
        {message && (
          <p role={failed ? "alert" : "status"} className={failed ? "error" : "muted"}>
            {message}
          </p>
        )}
        </div>
      </Card>
      <section className="stack" aria-labelledby="reviews-heading">
        <h2 id="reviews-heading" style={{ margin: 0, fontSize: "1.2rem" }}>
          {tr("reviews")}
        </h2>
        <Comments
          collection={`${API}/products/${id}/reviews`}
          item={`${API}/reviews`}
          me={user.username}
          rating="required"
          newestFirst
          label={tr("reviews")}
          placeholder={tr("your_review_only_buyers_with_a")}
          confirmDelete={tr("delete_your_review")}
          onChanged={product.reload}
        />
      </section>
    </>
  );
}

export default function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const productId = Number(id);
  return (
    <Shell title={tr("product")}>
      {(user) =>
        Number.isInteger(productId) && productId > 0 ? (
          <div style={{ width: "100%", minHeight: "100%", boxSizing: "border-box" }}>
            <ProductDetail id={productId} user={user} />
          </div>
        ) : (
          <ErrorLine message={tr("product_not_found")} />
        )
      }
    </Shell>
  );
}
