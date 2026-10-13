import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "@sn/theme.css";
import "./lab.css";

export const metadata: Metadata = { title: "Phòng thí nghiệm · Social Network" };
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi">
      <body>
        <main>{children}</main>
      </body>
    </html>
  );
}
