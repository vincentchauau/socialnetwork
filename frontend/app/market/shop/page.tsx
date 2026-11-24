"use client";

import Shop from "../Shop";
import { Shell } from "../shell";
import { tr } from "../i18n";

export default function ShopPage() {
  return <Shell title={tr("market")}>{() => <Shop />}</Shell>;
}
