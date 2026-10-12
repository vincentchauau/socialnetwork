"use client";

import { useEffect, useState } from "react";

import { CENTER_API, User, apiFetch, loadSession } from "@sn/api";
import { APPS } from "./apps";

type Session =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "error" }
  | { status: "signed-in"; user: User };

export default function HomePage() {
  const [session, setSession] = useState<Session>({ status: "loading" });
  const [logoutError, setLogoutError] = useState<string | null>(null);

  useEffect(() => {
    loadSession()
      .then((user) => setSession(user ? { status: "signed-in", user } : { status: "anonymous" }))
      .catch(() => setSession({ status: "error" }));
  }, []);

  async function logout() {
    setLogoutError(null);
    try {
      await apiFetch(`${CENTER_API}/auth/logout`, { method: "POST" });
      setSession({ status: "anonymous" });
    } catch {
      setLogoutError("Could not sign out. Please try again.");
    }
  }

  if (session.status === "loading") return <p className="muted">Loading…</p>;

  if (session.status === "error") {
    return (
      <div className="stack">
        <h1>Social Network</h1>
        <p role="alert" className="error">
          Could not reach the server. Please try again.
        </p>
      </div>
    );
  }

  if (session.status === "anonymous") {
    return (
      <div className="stack">
        <h1>Social Network</h1>
        <p>Sign in to use the apps.</p>
        <p>
          <a href="/login">Sign in or create an account</a>
        </p>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ margin: 0 }}>Hello, {session.user.username}</h1>
        <button className="secondary" onClick={logout}>
          Sign out
        </button>
      </div>
      {logoutError && (
        <p role="alert" className="error">
          {logoutError}
        </p>
      )}
      {APPS.map((app) => (
        <a key={app.href} href={app.href} className="card" style={{ textDecoration: "none" }}>
          <strong>{app.name}</strong>
          <div className="muted">{app.description}</div>
        </a>
      ))}
    </div>
  );
}
