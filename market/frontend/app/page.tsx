"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { API, Page, Product, errorText, formatMoney } from "./lib";
import { ErrorLine, Shell } from "./shell";

interface Filters {
  q: string;
  category: string;
  minPrice: string;
  maxPrice: string;
}

const EMPTY_FILTERS: Filters = { q: "", category: "", minPrice: "", maxPrice: "" };
const PAGE_SIZE = 12;

function toCents(input: string): string | null {
  const trimmed = input.trim();
  if (!/^\d{1,7}(\.\d{1,2})?$/.test(trimmed)) return null;
  return String(Math.round(Number(trimmed) * 100));
}

function buildQuery(filters: Filters, cursor: number | null): string {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.category.trim()) params.set("category", filters.category.trim());
  const min = toCents(filters.minPrice);
  const max = toCents(filters.maxPrice);
  if (min) params.set("min_price", min);
  if (max) params.set("max_price", max);
  if (cursor) params.set("cursor", String(cursor));
  return params.toString();
}

function ProductCard({ product }: { product: Product }) {
  return (
    <li className="card stack" style={{ gap: 6 }}>
      {product.image_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={product.image_url}
          alt=""
          loading="lazy"
          style={{ width: "100%", height: 140, objectFit: "cover", borderRadius: 6 }}
        />
      )}
      <Link href={`/products/${product.id}`} style={{ overflowWrap: "anywhere" }}>
        <strong>{product.name}</strong>
      </Link>
      <span>{formatMoney(product.price_cents, product.currency)}</span>
      <span className="muted">
        {product.rating_average === null
          ? "No reviews yet"
          : `★ ${product.rating_average} (${product.review_count})`}
        {" · "}
        {product.stock > 0 ? `${product.stock} in stock` : "Sold out"}
      </span>
      <span className="muted" style={{ overflowWrap: "anywhere" }}>
        by {product.seller_name} · {product.category}
      </span>
    </li>
  );
}

function Shop() {
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [items, setItems] = useState<Product[]>([]);
  const [nextCursor, setNextCursor] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPage = useCallback(async (active: Filters, cursor: number | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await apiFetch<Page<Product>>(`${API}/products?${buildQuery(active, cursor)}`);
      setItems((current) => (cursor ? [...current, ...page.items] : page.items));
      setNextCursor(page.next_cursor);
    } catch (failure) {
      setError(errorText(failure, "Could not load products"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchPage(filters, null);
  }, [filters, fetchPage]);

  function search(event: FormEvent) {
    event.preventDefault();
    setFilters(draft);
  }

  const field = (key: keyof Filters) => ({
    value: draft[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setDraft({ ...draft, [key]: event.target.value }),
  });

  return (
    <>
      <form className="stack" onSubmit={search} role="search">
        <div className="row">
          <input aria-label="Search products" placeholder="Search" maxLength={100} {...field("q")} />
          <button>Search</button>
        </div>
        <div className="row" style={{ flexWrap: "wrap" }}>
          <input aria-label="Category" placeholder="Category" maxLength={40} {...field("category")} />
          <input aria-label="Minimum price" placeholder="Min price" inputMode="decimal" {...field("minPrice")} />
          <input aria-label="Maximum price" placeholder="Max price" inputMode="decimal" {...field("maxPrice")} />
        </div>
      </form>
      <ErrorLine message={error} />
      {loading && items.length === 0 && <p className="muted">Loading…</p>}
      {!loading && !error && items.length === 0 && <p className="muted">No products found.</p>}
      <ul
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          display: "grid",
          gap: 12,
          gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 180px), 1fr))",
        }}
      >
        {items.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </ul>
      {nextCursor !== null && (
        <button className="secondary" disabled={loading} onClick={() => void fetchPage(filters, nextCursor)}>
          {loading ? "Loading…" : "Load more"}
        </button>
      )}
    </>
  );
}

export default function ShopPage() {
  return <Shell title="Market">{() => <Shop />}</Shell>;
}
