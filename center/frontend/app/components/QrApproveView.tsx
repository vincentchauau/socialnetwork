"use client";

import { ApiError } from "@sn/api";
import { FormEvent, useEffect, useState } from "react";

import Alert from "./Alert";
import { describeDevice, formatWhen } from "./SessionsMethod";
import { CARD, INPUT, LABEL, LINK_BUTTON, NOTE, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { useFragmentParam } from "../hooks/useUrlToken";
import {
  QR_EXPIRED_MESSAGE,
  QR_WRONG_CODE_MESSAGE,
  QrRequest,
  errorText,
  loadMe,
  qrApprove,
  qrDeny,
  qrDetails,
} from "../lib/auth";

export const VERIFY_CODE_LENGTH = 4;
const WRONG_CODE_STATUSES = [401, 403, 422];
const GONE_STATUSES = [404, 410];

type Stage =
  | { name: "loading" }
  | { name: "invalid" }
  | { name: "signedOut" }
  | { name: "expired" }
  | { name: "error"; text: string }
  | { name: "ready"; request: QrRequest }
  | { name: "approved" }
  | { name: "denied" };

function actionError(caught: unknown): { expired: boolean; text: string } {
  if (caught instanceof ApiError && GONE_STATUSES.includes(caught.status)) return { expired: true, text: QR_EXPIRED_MESSAGE };
  if (caught instanceof ApiError && WRONG_CODE_STATUSES.includes(caught.status)) return { expired: false, text: QR_WRONG_CODE_MESSAGE };
  return { expired: false, text: errorText(caught) };
}

/** Trang trên điện thoại đã đăng nhập: xem thiết bị đang yêu cầu, nhập mã xác nhận rồi Cho phép hoặc Từ chối. */
export default function QrApproveView() {
  const fragment = useFragmentParam("r");
  const [stage, setStage] = useState<Stage>({ name: "loading" });
  const [code, setCode] = useState("");
  const { busy, error, run, fail } = useAction();
  const requestId = fragment.ready ? fragment.value : null;

  useEffect(() => {
    if (!fragment.ready) return;
    if (!requestId) {
      setStage({ name: "invalid" });
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const me = await loadMe();
        if (cancelled) return;
        if (!me) return setStage({ name: "signedOut" });
        const request = await qrDetails(requestId);
        if (!cancelled) setStage({ name: "ready", request });
      } catch (caught) {
        if (cancelled) return;
        const failure = actionError(caught);
        // A wrong-code status on a read is not a wrong code: show the generic text.
        setStage(failure.expired ? { name: "expired" } : { name: "error", text: errorText(caught) });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fragment.ready, requestId]);

  async function settle(call: () => Promise<unknown>, next: Stage) {
    try {
      await call();
      setStage(next);
    } catch (caught) {
      const failure = actionError(caught);
      if (failure.expired) setStage({ name: "expired" });
      else throw new Error(failure.text);
    }
  }

  function approve(event: FormEvent) {
    event.preventDefault();
    if (!requestId) return;
    const typed = code.trim();
    if (typed.length !== VERIFY_CODE_LENGTH) return fail(`Hãy nhập mã xác nhận gồm ${VERIFY_CODE_LENGTH} ký tự`);
    void run(() => settle(() => qrApprove(requestId, typed), { name: "approved" }));
  }

  function deny() {
    if (!requestId) return;
    void run(() => settle(() => qrDeny(requestId), { name: "denied" }));
  }

  return (
    <main className={CARD}>
      <h1 className="text-2xl font-bold mb-4">Đăng nhập bằng mã QR</h1>
      {stage.name === "loading" && <p role="status" className={NOTE}>Đang tải...</p>}
      {stage.name === "invalid" && (
        <>
          <Alert text="Liên kết không hợp lệ. Hãy quét lại mã QR trên màn hình đăng nhập." />
          <a href="/login" className={`${LINK_BUTTON} block text-center`}>Về trang đăng nhập</a>
        </>
      )}
      {stage.name === "signedOut" && (
        <>
          <p role="alert" className="text-sm text-red-600 mb-2">
            Bạn cần đăng nhập trên điện thoại này trước, rồi quét lại mã QR.
          </p>
          <a href="/login" className={`${PRIMARY_BUTTON} block text-center`}>Đăng nhập</a>
        </>
      )}
      {stage.name === "expired" && (
        <>
          <Alert text={QR_EXPIRED_MESSAGE} />
          <a href="/" className={`${LINK_BUTTON} block text-center`}>Về trang chủ</a>
        </>
      )}
      {stage.name === "error" && <Alert text={stage.text} />}
      {stage.name === "approved" && (
        <p role="status" className="text-sm text-green-700">Đã cho phép đăng nhập trên thiết bị kia.</p>
      )}
      {stage.name === "denied" && <p role="status" className="text-sm text-green-700">Đã từ chối yêu cầu đăng nhập.</p>}
      {stage.name === "ready" && (
        <form onSubmit={approve} aria-label="Cho phép đăng nhập">
          <section aria-label="Thiết bị đang yêu cầu đăng nhập" className="border rounded p-3 mb-3 text-sm">
            <h2 className="font-bold mb-1">Thiết bị đang yêu cầu đăng nhập</h2>
            <p>{describeDevice(stage.request.requester_user_agent)}</p>
            <p>Địa chỉ IP: {stage.request.requester_ip ?? "không rõ"}</p>
            <p>Lúc: {formatWhen(stage.request.created_at)}</p>
          </section>
          <label htmlFor="qr-verify-code" className={LABEL}>Mã xác nhận hiển thị trên màn hình kia</label>
          <input id="qr-verify-code" value={code} autoComplete="off" autoCapitalize="characters" spellCheck={false}
                 maxLength={VERIFY_CODE_LENGTH} onChange={(e) => setCode(e.target.value.toUpperCase())}
                 className={`${INPUT} text-center text-2xl font-mono tracking-widest`} />
          <p className={NOTE}>Chỉ bấm Cho phép nếu chính bạn đang đăng nhập và mã khớp.</p>
          <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>{busy ? "Đang xử lý..." : "Cho phép"}</button>
          <button type="button" disabled={busy} onClick={deny} className={`${SECONDARY_BUTTON} mt-2`}>Từ chối</button>
          <Alert text={error} />
        </form>
      )}
    </main>
  );
}
