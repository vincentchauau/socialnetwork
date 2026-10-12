"use client";

import { FormEvent, use, useCallback, useState } from "react";

import { User, apiFetch } from "@sn/api";
import { API, MAX_CART_QUANTITY, Product, Review, errorText, formatDate, formatMoney } from "../../lib";
import { ErrorLine, Shell, useLoad } from "../../shell";

const REVIEW_MAX = 1000;
const RATINGS = [5, 4, 3, 2, 1];

function ReviewSection({ productId, reload }: { productId: number; reload: () => void }) {
  const loadReviews = useCallback(
    () => apiFetch<Review[]>(`${API}/products/${productId}/reviews`),
    [productId],
  );
  const reviews = useLoad(loadReviews, (e) => errorText(e, "Could not load reviews"));
  const [rating, setRating] = useState("5");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      await apiFetch(`${API}/products/${productId}/reviews`, {
        method: "POST",
        body: JSON.stringify({ rating: Number(rating), text }),
      });
      setText("");
      setFailed(false);
      setMessage("Thanks for your review!");
      reviews.reload();
      reload();
    } catch (error) {
      setFailed(true);
      setMessage(errorText(error, "Could not post review"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="stack" aria-labelledby="reviews-heading">
      <h2 id="reviews-heading" style={{ margin: 0, fontSize: "1.2rem" }}>
        Reviews
      </h2>
      <ErrorLine message={reviews.error} />
      {reviews.loading && !reviews.data && <p className="muted">Loading…</p>}
      {reviews.data && reviews.data.length === 0 && <p className="muted">No reviews yet.</p>}
      <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {reviews.data?.map((item) => (
          <li key={item.id} className="card">
            <strong>{item.username}</strong> ·{" "}
            <span aria-label={`${item.rating} out of 5`} role="img">
              {"★".repeat(item.rating)}
            </span>{" "}
            <span className="muted">{formatDate(item.created_at)}</span>
            <div style={{ overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}>{item.text}</div>
          </li>
        ))}
      </ul>
      <form className="stack" onSubmit={submit}>
        <label className="stack" style={{ gap: 4 }}>
          Rating
          <select style={{ font: "inherit", padding: 8 }} value={rating} onChange={(event) => setRating(event.target.value)}>
            {RATINGS.map((value) => (
              <option key={value} value={value}>
                {value} / 5
              </option>
            ))}
          </select>
        </label>
        <label className="stack" style={{ gap: 4 }}>
          Your review (only buyers with a delivered order can review)
          <textarea
            style={{ font: "inherit", padding: 8 }}
            value={text}
            maxLength={REVIEW_MAX}
            rows={3}
            onChange={(event) => setText(event.target.value)}
          />
        </label>
        <button disabled={busy}>{busy ? "Posting…" : "Post review"}</button>
        {message && (
          <p role={failed ? "alert" : "status"} className={failed ? "error" : "muted"}>
            {message}
          </p>
        )}
      </form>
    </section>
  );
}

function ProductDetail({ id, user }: { id: number; user: User }) {
  const load = useCallback(() => apiFetch<Product>(`${API}/products/${id}`), [id]);
  const product = useLoad(load, (e) => errorText(e, "Could not load product"));
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
      setMessage("Added to your cart.");
    } catch (error) {
      setFailed(true);
      setMessage(errorText(error, "Could not update cart"));
    } finally {
      setBusy(false);
    }
  }

  const item = product.data;
  if (product.loading && !item) return <p className="muted">Loading…</p>;
  if (!item) return <ErrorLine message={product.error ?? "Product not found"} />;
  const own = item.seller_id === user.id;

  return (
    <>
      <div className="card stack">
        {item.image_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={item.image_url} alt="" style={{ maxWidth: "100%", maxHeight: 280, objectFit: "contain" }} />
        )}
        <h2 style={{ margin: 0, overflowWrap: "anywhere" }}>{item.name}</h2>
        <strong>{formatMoney(item.price_cents, item.currency)}</strong>
        <span className="muted">
          by {item.seller_name} · {item.category} ·{" "}
          {item.rating_average === null
            ? "No reviews yet"
            : `★ ${item.rating_average} (${item.review_count})`}
        </span>
        <p style={{ margin: 0, overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}>{item.description}</p>
        <span className="muted">{item.stock > 0 ? `${item.stock} in stock` : "Sold out"}</span>
        {own ? (
          <p className="muted">This is your product.</p>
        ) : (
          <form className="row" onSubmit={addToCart}>
            <input
              type="number"
              aria-label="Quantity"
              min={1}
              max={MAX_CART_QUANTITY}
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              style={{ maxWidth: 90, flex: "none" }}
            />
            <button disabled={busy || item.stock === 0}>Add to cart</button>
          </form>
        )}
        {message && (
          <p role={failed ? "alert" : "status"} className={failed ? "error" : "muted"}>
            {message}
          </p>
        )}
      </div>
      <ReviewSection productId={id} reload={product.reload} />
    </>
  );
}

export default function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const productId = Number(id);
  return (
    <Shell title="Product">
      {(user) =>
        Number.isInteger(productId) && productId > 0 ? (
          <ProductDetail id={productId} user={user} />
        ) : (
          <ErrorLine message="Product not found" />
        )
      }
    </Shell>
  );
}
