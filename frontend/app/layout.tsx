import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { ConfirmHost } from "@sn/compounds/Dialogs";
import { LocaleProvider } from "@sn/lib/i18n";
import "@sn/lib/base.css";
import "@sn/lib/theme.css";
import "@sn/lib/utilities.css";
import "@sn/compounds/crudTable.css";

export const metadata: Metadata = {
  title: "Mạng xã hội",
  description: "Một chỗ cho nhu cầu riêng và nhóm: tài khoản, trò chuyện, việc làm, học tập, mua bán…",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

/** Only what every app shares; each app has its own layout (and its own `.app-<slug>` wrapper for its CSS). */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi">
      <body>
        <LocaleProvider>
          {children}
          <ConfirmHost />
        </LocaleProvider>
      </body>
    </html>
  );
}
