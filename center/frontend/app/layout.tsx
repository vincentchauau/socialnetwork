import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mạng xã hội",
  description: "Đăng nhập bằng mật khẩu, Google và sinh trắc học",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi">
      <body className="antialiased px-2 pb-10">{children}</body>
    </html>
  );
}
