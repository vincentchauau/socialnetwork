"use client";

import { useEffect, useState } from "react";

import { type User, loadSession } from "../api";

export type Auth =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "error" }
  | { status: "signed-in"; user: User };

/** The current session: loading, then signed in, signed out, or an error when the server could not be reached. */
export function useSession(): Auth {
  const [auth, setAuth] = useState<Auth>({ status: "loading" });

  useEffect(() => {
    loadSession()
      .then((user) => setAuth(user ? { status: "signed-in", user } : { status: "anonymous" }))
      .catch(() => setAuth({ status: "error" }));
  }, []);

  return auth;
}
