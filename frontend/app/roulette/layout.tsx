import type { Metadata } from "next";
import type { ReactNode } from "react";
import AppFrame from "../chat/dock/AppFrame";
import "../chat/chatwork.css";
import "./roulette.css";

export const metadata: Metadata = { title: "Roulette · Social Network" };

export default function RouletteLayout({ children }: { children: ReactNode }) {
  return (
    <AppFrame name="Roulette" app="roulette" css="app-roulette app-chat">{children}</AppFrame>
  );
}
