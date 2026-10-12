"use client";

import type { ReactNode } from "react";

import type { User } from "@sn/api";
import { Auth, useSession } from "./useSession";

interface GateProps {
  title: string;
  children: (user: User) => ReactNode;
}

/** Handles loading / error / signed-out states; renders children for a signed-in user. */
export function Gate({ title, children }: GateProps) {
  const auth: Auth = useSession();
  if (auth.status === "loading") return <p className="muted">Loading…</p>;
  if (auth.status === "error") {
    return (
      <div className="stack">
        <a href="/">← Home</a>
        <h1>{title}</h1>
        <p role="alert" className="error">
          Could not reach the server. Please try again.
        </p>
      </div>
    );
  }
  if (auth.status === "anonymous") {
    return (
      <div className="stack">
        <a href="/">← Home</a>
        <h1>{title}</h1>
        <p>
          Please <a href="/login">sign in</a> first.
        </p>
      </div>
    );
  }
  return <>{children(auth.user)}</>;
}
