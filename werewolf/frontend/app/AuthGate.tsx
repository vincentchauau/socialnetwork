"use client";

import type { ReactNode } from "react";

import type { User } from "@sn/api";
import { useSession } from "./useSession";

/** Shows loading / error / signed-out states; renders children only for a signed-in user. */
export default function AuthGate({
  title,
  children,
}: {
  title: string;
  children: (user: User) => ReactNode;
}) {
  const auth = useSession();

  if (auth.status === "loading") return <p className="muted">Loading…</p>;

  if (auth.status === "error") {
    return (
      <div className="stack">
        <h1>{title}</h1>
        <p role="alert" className="error">
          Could not reach the server. Please try again.
        </p>
        <a href="/">← Home</a>
      </div>
    );
  }

  if (auth.status === "anonymous") {
    return (
      <div className="stack">
        <h1>{title}</h1>
        <p>
          Please <a href="/login">sign in</a> first.
        </p>
        <a href="/">← Home</a>
      </div>
    );
  }

  return <>{children(auth.user)}</>;
}
