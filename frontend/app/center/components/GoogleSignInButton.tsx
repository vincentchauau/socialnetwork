"use client";

import { useEffect, useRef, useState } from "react";
import { tr } from "../i18n";

const GSI_SRC = "https://accounts.google.com/gsi/client";

interface GoogleId {
  initialize: (config: { client_id: string; callback: (response: { credential?: string }) => void }) => void;
  renderButton: (element: HTMLElement, options: Record<string, unknown>) => void;
}
declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } };
  }
}

let scriptPromise: Promise<void> | null = null;

function loadGoogleScript(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (!scriptPromise) {
    scriptPromise = new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = GSI_SRC;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        script.remove();
        scriptPromise = null; // allow a retry later
        reject(new Error("Google script failed to load"));
      };
      document.head.appendChild(script);
    });
  }
  return scriptPromise;
}

interface Props {
  clientId: string;
  onCredential: (idToken: string) => void;
  onError: (message: string) => void;
}

/** Renders Google's own button; the script is only fetched when a client id is configured. */
export default function GoogleSignInButton({ clientId, onCredential, onError }: Props) {
  const holder = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const callbacks = useRef({ onCredential, onError });
  callbacks.current = { onCredential, onError };

  useEffect(() => {
    let cancelled = false;
    loadGoogleScript()
      .then(() => {
        const google = window.google?.accounts?.id;
        if (cancelled || !google || !holder.current) return;
        google.initialize({
          client_id: clientId,
          callback: ({ credential }) =>
            credential
              ? callbacks.current.onCredential(credential)
              : callbacks.current.onError(tr("dang_nhap_google_that_bai")),
        });
        google.renderButton(holder.current, { theme: "outline", size: "large" });
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  if (failed) {
    return (
      <p role="alert" className="text-sm text-line">
        {tr("khong_tai_duoc_dang_nhap_google")}
      </p>
    );
  }
  return <div ref={holder} aria-label={tr("dang_nhap_bang_google")} />;
}
