"use client";

import { ReactNode } from "react";

import AuthGate from "@sn/compounds/AuthGate";
import type { User } from "@sn/api";
import { tr } from "./i18n";

/** Page frame: the sign-in check and the title. */
export function Shell({ title, children }: { title: string; children: (user: User) => ReactNode }) {
  return (
    <AuthGate title={title} heading>
      {children}
    </AuthGate>
  );
}

export { useLoad,  } from "@sn/lib/hooks";

export function ErrorLine({ message }: { message: string | null }) {
  return message ? (
    <p role="alert" className="error">
      {message}
    </p>
  ) : null;
}
