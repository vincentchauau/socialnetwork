"use client";

import { ReactNode, useState } from "react";

import Alert from "./Alert";
import { CARD, LINK_BUTTON, PRIMARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { useUrlToken } from "../hooks/useUrlToken";

interface Props {
  title: string;
  intro: string;
  button: string;
  missing: string;
  /** Runs the one-time call (and any redirect) when the person presses the button. */
  confirm: (token: string) => Promise<void>;
  success: ReactNode;
  failure: ReactNode;
}

/**
 * Click-to-confirm for emailed links. Nothing is sent on page load (mail scanners that open links must not
 * consume the token); the request happens only when the person presses the button.
 */
export default function TokenConfirm({ title, intro, button, missing, confirm, success, failure }: Props) {
  const url = useUrlToken();
  const [outcome, setOutcome] = useState<"idle" | "done" | "failed">("idle");
  const { busy, run } = useAction();

  if (!url.ready) return <p role="status" className="text-center mt-10">Đang tải...</p>;
  const token = url.token;

  async function onClick() {
    if (!token) return;
    const ok = await run(() => confirm(token));
    setOutcome(ok ? "done" : "failed");
  }

  return (
    <main className={CARD}>
      <h1 className="text-2xl font-bold mb-4">{title}</h1>
      {outcome === "done" ? (
        success
      ) : outcome === "failed" ? (
        failure
      ) : !token ? (
        <>
          <Alert text={missing} />
          <a href="/login" className={`${LINK_BUTTON} block text-center`}>Về trang đăng nhập</a>
        </>
      ) : (
        <>
          <p className="text-sm text-gray-600 mb-4">{intro}</p>
          <button type="button" disabled={busy} onClick={() => void onClick()} className={PRIMARY_BUTTON}>
            {busy ? "Đang xử lý..." : button}
          </button>
        </>
      )}
    </main>
  );
}
