"use client";

import { useEffect, useState } from "react";

import { User, loadSession } from "@sn/api";

/** /auth/me also returns the role; the shared User type does not declare it. */
export type SessionUser = User & { role?: string };

export type Auth =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "error" }
  | { status: "signed-in"; user: SessionUser };

export function useSession(): Auth {
  const [auth, setAuth] = useState<Auth>({ status: "loading" });

  useEffect(() => {
    loadSession()
      .then((user) => setAuth(user ? { status: "signed-in", user } : { status: "anonymous" }))
      .catch(() => setAuth({ status: "error" }));
  }, []);

  return auth;
}
