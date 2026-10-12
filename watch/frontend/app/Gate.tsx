"use client";

import { ReactNode, useEffect, useState } from "react";

import { User, loadSession } from "@sn/api";

type Auth =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "error" }
  | { status: "signed-in"; user: User };

/** Renders the page shell and, once signed in, the page body. */
export default function Gate({
  title,
  children,
}: {
  title: string;
  children: (user: User) => ReactNode;
}) {
  const [auth, setAuth] = useState<Auth>({ status: "loading" });

  useEffect(() => {
    loadSession()
      .then((user) => setAuth(user ? { status: "signed-in", user } : { status: "anonymous" }))
      .catch(() => setAuth({ status: "error" }));
  }, []);

  return (
    <div className="stack">
      <nav className="nav" aria-label="Watch">
        <a href="/">← Home</a>
        <a href="/watch">Catalog</a>
        <a href="/watch/upload">Upload</a>
        <a href="/watch/watchlist">Watchlist</a>
        <a href="/watch/history">History</a>
      </nav>
      <h1>{title}</h1>
      {auth.status === "loading" && <p role="status">Loading…</p>}
      {auth.status === "error" && (
        <p className="error" role="alert">
          Could not check your session. Please try again.
        </p>
      )}
      {auth.status === "anonymous" && (
        <p>
          <a href="/login">Sign in</a> to use Watch.
        </p>
      )}
      {auth.status === "signed-in" && children(auth.user)}
    </div>
  );
}
