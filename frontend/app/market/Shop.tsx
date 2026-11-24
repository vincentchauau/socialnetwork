"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { FacetGridView } from "@sn/compounds/SplitPanel";
import FacetView, { type Facet } from "@sn/compounds/FacetView";
import { GridView } from "@sn/compounds/GalleryView";
import Button from "@sn/elements/Button";
import { usePagedList } from "@sn/lib/hooks";
import { API, Page, Product, errorText, formatMoney } from "./lib";
import { notifyCartChanged } from "./cartEvents";
import { ErrorLine } from "./shell";
import { tr } from "./i18n";
import TextBox from "@sn/elements/TextBox";
import Card from "@sn/elements/Card";

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

const PICTURE: React.CSSProperties = { width: "100%", aspectRatio: "4 / 3", objectFit: "cover", borderRadius: 6, display: "block" };

function Stars({ average, count }: { average: number | null; count: number }) {
  if (average === null) return <span className="muted">{tr("no_reviews_yet")}</span>;
  const full = Math.round(average);
  return (
    <span aria-label={`${average} / 5`}>
      <span aria-hidden="true">{"★".repeat(full)}{"☆".repeat(5 - full)}</span> <span className="muted">({count})</span>
    </span>
  );
}

function ProductCard({ product }: { product: Product }) {
  const [added, setAdded] = useState<"idle" | "busy" | "done" | "failed">("idle");
  async function addToCart() {
    setAdded("busy");
    try {
      await apiFetch(`${API}/cart/items/${product.id}`, { method: "PUT", body: JSON.stringify({ quantity: 1 }) });
      setAdded("done");
      notifyCartChanged();
    } catch {
      setAdded("failed");
    }
  }
  return (
    <Card stack as="article" style={{ gap: 6, height: "100%", boxSizing: "border-box" }}>
      <Link href={`/market/products/${product.id}`} aria-hidden="true" tabIndex={-1}>
        {product.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={product.image_url} alt="" loading="lazy" style={PICTURE} />
        ) : (
          <div aria-hidden="true" style={{ ...PICTURE, display: "grid", placeItems: "center", border: "1px solid var(--line)", fontSize: "2rem" }}>
            {product.name.slice(0, 1).toUpperCase()}
          </div>
        )}
      </Link>
      <Link href={`/market/products/${product.id}`} style={{ overflowWrap: "anywhere" }}>
        <strong>{product.name}</strong>
      </Link>
      <strong style={{ fontSize: "1.1rem" }}>{formatMoney(product.price_cents, product.currency)}</strong>
      <Stars average={product.rating_average} count={product.review_count} />
      <span className="muted">{product.stock > 0 ? tr("p0_in_stock", { p0: product.stock }) : tr("sold_out")}</span>
      <span className="muted" style={{ overflowWrap: "anywhere" }}>
        {tr("by")} {product.seller_username} · {product.category}
      </span>
      <Button type="button" size="sm" variant={added === "done" ? "secondary" : "primary"} disabled={product.stock <= 0 || added === "busy"} onClick={() => void addToCart()} style={{ marginTop: "auto" }}>
        {added === "done" ? `${tr("add_to_cart")} ✓` : added === "failed" ? tr("could_not_update_cart") : tr("add_to_cart")}
      </Button>
    </Card>
  );
}

export default function Shop({ initialQuery = "" }: { initialQuery?: string }) {
  const start = { ...EMPTY_FILTERS, q: initialQuery };
  const [draft, setDraft] = useState<Filters>(start);
  const [filters, setFilters] = useState<Filters>(start);
  const [categories, setCategories] = useState<Facet[]>([]);
  const list = usePagedList<Product, number>(
    (cursor) => apiFetch<Page<Product>>(`${API}/products?${buildQuery(filters, cursor)}`),
    [filters],
    (failure) => errorText(failure, tr("could_not_load_products")),
  );

  useEffect(() => {
    apiFetch<Facet[]>(`${API}/categories`).then(setCategories, () => undefined); // the tree is a help, not worth an error
  }, []);

  function apply(next: Filters) {
    setDraft(next);
    setFilters(next);
  }

  function search(event: FormEvent) {
    event.preventDefault();
    setFilters(draft);
  }

  const field = (key: keyof Filters) => ({
    value: draft[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) => setDraft({ ...draft, [key]: event.target.value }),
  });

  const filtersPane = (
    <div className="stack">
      <FacetView label={tr("categories")} allLabel={tr("all_categories")} facets={categories} value={filters.category} onChange={(category) => apply({ ...draft, category })} />
      <form className="stack" onSubmit={search} role="search">
        <TextBox aria-label={tr("search_products")} placeholder={tr("search")} maxLength={100} {...field("q")} />
        <div className="row">
          <TextBox aria-label={tr("minimum_price")} placeholder={tr("min_price")} inputMode="decimal" {...field("minPrice")} />
          <TextBox aria-label={tr("maximum_price")} placeholder={tr("max_price")} inputMode="decimal" {...field("maxPrice")} />
        </div>
        <div className="row">
          <button type="submit" hidden aria-hidden="true" tabIndex={-1} />
          <Button type="button" variant="secondary" onClick={() => apply(EMPTY_FILTERS)}>{tr("reset")}</Button>
        </div>
      </form>
    </div>
  );

  return (
    <FacetGridView name="market" filtersLabel={tr("filters")} resultsLabel={tr("products")} filters={filtersPane}>
      <div className="stack">
        <ErrorLine message={list.error} />
        {list.loading && <p className="muted">{tr("loading")}</p>}
        {!list.loading && !list.error && list.items.length === 0 && <p className="muted">{tr("no_products_found")}</p>}
        <GridView items={list.items} itemKey={(product) => product.id} renderItem={(product) => <ProductCard product={product} />} label={tr("products")} minColumnWidth={190} gap={12} />
        {list.hasMore && (
          <Button variant="secondary" disabled={list.loadingMore} onClick={list.loadMore}>
            {list.loadingMore ? tr("loading") : tr("load_more")}
          </Button>
        )}
      </div>
    </FacetGridView>
  );
}

