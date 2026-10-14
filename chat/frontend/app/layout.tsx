import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./reboot.css";
import "./chatwork.css";

export const metadata: Metadata = { title: "Chat · Social Network" };
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi" className="fullColumnContainer">
      <body className="fullColumnContainer">{children}</body>
    </html>
  );
}
