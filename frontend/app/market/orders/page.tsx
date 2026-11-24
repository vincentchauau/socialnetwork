"use client";

import OrderList from "./OrderList";
import { Shell } from "../shell";
import { tr } from "../i18n";

export default function OrdersPage() {
  return <Shell title={tr("my_orders")}>{() => <OrderList />}</Shell>;
}
