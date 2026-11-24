"use client";

import CartView from "./CartView";
import { Shell } from "../shell";
import { tr } from "../i18n";

export default function CartPage() {
  return <Shell title={tr("your_cart")}>{() => <CartView />}</Shell>;
}
