import type { Metadata } from "next";
import type { ReactNode } from "react";
import "@sn/theme.css";
import "./jobs.css";

export const metadata: Metadata = { title: "Jobs · Social Network" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <main>{children}</main>
      </body>
    </html>
  );
}
