import type { Metadata } from "next";
import type { ReactNode } from "react";
import "@sn/theme.css";

export const metadata: Metadata = { title: "Photos · Social Network" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <main>{children}</main>
      </body>
    </html>
  );
}
