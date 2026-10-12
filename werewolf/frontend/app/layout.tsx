import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "@sn/theme.css";

export const metadata: Metadata = { title: "Werewolf · Social Network" };
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <main>{children}</main>
      </body>
    </html>
  );
}
