import type { Metadata } from "next";
import type { ReactNode } from "react";
import AppFrame from "../chat/dock/AppFrame";
import "../chat/chatwork.css";

export const metadata: Metadata = { title: "File · Social Network" };

export default function FileLayout({ children }: { children: ReactNode }) {
  return (
    <AppFrame name="File" app="file" css="app-file app-chat">{children}</AppFrame>
  );
}
