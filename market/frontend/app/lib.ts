import { ApiError } from "@sn/api";

export const API = "/api/market";

export interface Product {
  id: number;
  seller_id: number;
  seller_name: string;
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

export type OrderStatus = "pending_payment" | "paid" | "shipped" | "delivered" | "cancelled";

export interface OrderItem {
  product_id: number;
  name: string;
  unit_price_cents: number;
  quantity: number;
  line_total_cents: number;
}

export interface Order {
  id: number;
  status: OrderStatus;
  currency: string;
  total_cents: number;
  buyer_name: string;
  created_at: string;
  updated_at: string;
  items: OrderItem[];
}

export interface Review {
  id: number;
  product_id: number;
  username: string;
  rating: number;
  text: string;
  created_at: string;
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
  pending_payment: "Awaiting payment",
  paid: "Paid",
  shipped: "Shipped",
  delivered: "Delivered",
  cancelled: "Cancelled",
};

export function errorText(error: unknown, fallback = "Something went wrong"): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
