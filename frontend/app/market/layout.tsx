import type { Metadata } from "next";
import type { ReactNode } from "react";
import AppFrame from "../chat/dock/AppFrame";

export const metadata: Metadata = { title: "Market · Social Network" };

export default function MarketLayout({ children }: { children: ReactNode }) {
  return (
    <AppFrame name="Market" app="market" css="app-market" except={["/market/products/"]}>{children}</AppFrame>
  );
}
