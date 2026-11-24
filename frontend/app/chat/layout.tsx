import type { Metadata } from "next";
import type { ReactNode } from "react";
import AppFrame from "./dock/AppFrame";
import "./chatwork.css";

export const metadata: Metadata = { title: "Chat · Social Network" };

export default function ChatLayout({ children }: { children: ReactNode }) {
  return (
    <AppFrame name="Chat" app="chat" css="app-chat" except={["/chat"]}>{children}</AppFrame>
  );
}
