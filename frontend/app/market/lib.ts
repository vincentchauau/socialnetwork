import { tr } from "./i18n";
import { intlLocale } from "@sn/lib/i18n";

export const API = "/api/market";

export interface Product {
  id: number;
  seller_id: number;
  seller_username: string;
  name: string;
  description: string;
  price_cents: number;
  currency: string;
  stock: number;
  image_url: string | null;
  category: string;
  rating_average: number | null;
  review_count: number;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  next_cursor: number | null;
}

export interface CartLine {
  product_id: number;
  name: string;
  image_url: string | null;
  unit_price_cents: number;
  quantity: number;
  line_total_cents: number;
  stock: number;
}

export interface Cart {
  items: CartLine[];
  currency: string;
  item_count: number;
  total_cents: number;
}

export type OrderStatus = "pending_payment" | "paid" | "shipped" | "delivered" | "cancelled" | "return_requested" | "returned";

export interface OrderItem {
  product_id: number;
  name: string;
  unit_price_cents: number;
  quantity: number;
  line_total_cents: number;
  discount_cents?: number;
}

export interface Order {
  id: number;
  status: OrderStatus;
  currency: string;
  total_cents: number;
  buyer_username: string;
  created_at: string;
  items: OrderItem[];
  discount_code?: string | null;
  discount_cents?: number;
  delivered_at?: string | null;
}

export const MAX_CART_QUANTITY = 99;
const DEFAULT_CURRENCY = "USD";
const DEFAULT_LOCALE = "en-US";

/** Formats integer minor units (cents) as currency text. Never uses float math on stored values. */
export function formatMoney(minorUnits: number, currency: string = DEFAULT_CURRENCY): string {
  const formatter = new Intl.NumberFormat(DEFAULT_LOCALE, { style: "currency", currency });
  const digits = formatter.resolvedOptions().maximumFractionDigits ?? 2;
  return formatter.format(minorUnits / 10 ** digits);
}

/** Parses a user-typed decimal price ("12.50") into integer cents, or null when invalid. */
export function parsePriceToCents(input: string): number | null {
  const match = /^(\d{1,7})(?:\.(\d{1,2}))?$/.exec(input.trim());
  if (!match) return null;
  const cents = Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0"));
  return cents >= 1 ? cents : null;
}

export const STATUS_LABELS: Record<OrderStatus, string> = {
  get pending_payment() { return tr("awaiting_payment"); },
  get paid() { return tr("paid"); },
  get shipped() { return tr("shipped"); },
  get delivered() { return tr("delivered"); },
  get cancelled() { return tr("cancelled"); },
  get return_requested() { return tr("return_requested"); },
  get returned() { return tr("returned"); },
};

export { errorText } from "@sn/api";

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(intlLocale());
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
