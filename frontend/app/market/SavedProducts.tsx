"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import Button from "@sn/elements/Button";
import { API, Product, errorText, formatMoney } from "./lib";
import { tr } from "./i18n";

/** The products the person saved to look at again: each opens its page, and can be unsaved here. */
export default function SavedProducts() {
  const [items, setItems] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    apiFetch<Product[]>(`${API}/me/saved-products`)
      .then((list) => { if (alive) setItems(list); })
      .catch((failure: unknown) => { if (alive) setError(errorText(failure, tr("could_not_load_saved_products"))); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  async function unsave(id: number) {
    try {
      await apiFetch(`${API}/products/${id}/save`, { method: "DELETE" });
      setItems((current) => current.filter((item) => item.id !== id));
    } catch (failure) {
      setError(errorText(failure, tr("could_not_load_saved_products")));
    }
  }

  if (loading) return <p role="status" className="muted">{tr("loading")}</p>;
  if (error) return <p role="alert" className="error">{error}</p>;
  if (items.length === 0) return <p className="muted">{tr("you_have_no_saved_products_yet")}</p>;
  return (
    <ul className="list" aria-label={tr("saved_products")}>
      {items.map((item) => (
        <li key={item.id} className="row" style={{ justifyContent: "space-between" }}>
          <Link href={`/market/products/${item.id}`}>{item.name}</Link>
          <span className="muted">{formatMoney(item.price_cents, item.currency)}</span>
          <Button type="button" size="sm" variant="secondary" onClick={() => void unsave(item.id)}>{tr("unsave_product")}</Button>
        </li>
      ))}
    </ul>
  );
}
