"use client";

import type { ReactNode } from "react";

import type { User } from "../api";
import Alert from "../elements/Alert";
import { intlLocale } from "../lib/i18n";
import { useSession } from "../lib/useSession";

export interface AuthGateLabels {
  loading: string;
  error: string;
  /** "Please " + link + " first." around the sign-in link. */
  signInBefore: string;
  signInLink: string;
  signInAfter: string;
  home: string;
}

const DEFAULT_LABELS: AuthGateLabels = {
  loading: "Loading…",
  error: "Could not reach the server. Please try again.",
  signInBefore: "Please ",
  signInLink: "sign in",
  signInAfter: " first.",
  home: "← Home",
};

export const AUTH_GATE_LABELS_VI: AuthGateLabels = {
  loading: "Đang tải…",
  error: "Không kết nối được máy chủ. Hãy thử lại.",
  signInBefore: "Hãy ",
  signInLink: "đăng nhập",
  signInAfter: " trước.",
  home: "← Trang chủ",
};

export interface AuthGateProps {
  title: string;
  /** Show the title above the page for a signed-in user (the page frame of an app). */
  heading?: boolean;
  /** Rendered only for a signed-in user, which it receives. */
  children: (user: User) => ReactNode;
  labels?: Partial<AuthGateLabels>;
}

const STACK = { display: "flex", flexDirection: "column", gap: 12 } as const;

/** Shows loading, server-error and signed-out states itself; renders `children` only for a signed-in user. */
export function AuthGate({ title, heading = false, children, labels }: AuthGateProps) {
  const text = { ...(intlLocale().startsWith("en") ? DEFAULT_LABELS : AUTH_GATE_LABELS_VI), ...labels }; // the words of the language the site is in, unless told otherwise
  const auth = useSession();

  if (auth.status === "loading") return <p style={{ margin: 0 }}>{text.loading}</p>;
  if (auth.status === "signed-in") {
    if (!heading) return <>{children(auth.user)}</>;
    return (
      <div className="stack">
        <h1 style={{ margin: 0 }}>{title}</h1>
        {children(auth.user)}
      </div>
    );
  }

  return (
    <div style={STACK}>
      <h1>{title}</h1>
      {auth.status === "error" ? (
        <Alert>{text.error}</Alert>
      ) : (
        <p style={{ margin: 0 }}>
          {text.signInBefore}
          <a href="/user">{text.signInLink}</a>
          {text.signInAfter}
        </p>
      )}
      <a href="/">{text.home}</a>
    </div>
  );
}

export default AuthGate;
