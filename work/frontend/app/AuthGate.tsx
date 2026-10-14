"use client";

import type { ReactNode } from "react";

import type { SessionUser } from "./useSession";
import { useSession } from "./useSession";

/** Shows loading / error / signed-out states; renders children only for a signed-in user. */
export default function AuthGate({
  title,
  children,
}: {
  title: string;
  children: (user: SessionUser) => ReactNode;
}) {
  const auth = useSession();

  if (auth.status === "loading") return <p style={{ lineHeight: 1.5 }}>Đang tải…</p>;

  if (auth.status === "error") {
    return (
      <div className="columnContainer">
        <h1>{title}</h1>
        <p role="alert" style={{ lineHeight: 1.5 }}>
          Không kết nối được máy chủ. Hãy thử lại.
        </p>
        <a href="/">← Trang chủ</a>
      </div>
    );
  }

  if (auth.status === "anonymous") {
    return (
      <div className="columnContainer">
        <h1>{title}</h1>
        <p>
          Hãy <a href="/login">đăng nhập</a> trước.
        </p>
        <a href="/">← Trang chủ</a>
      </div>
    );
  }

  return <>{children(auth.user)}</>;
}
