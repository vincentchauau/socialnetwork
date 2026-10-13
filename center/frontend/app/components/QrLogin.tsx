"use client";

import { ApiError } from "@sn/api";
import { useCallback, useEffect, useRef, useState } from "react";

import Alert from "./Alert";
import QrImage from "./QrImage";
import { NOTE, PRIMARY_BUTTON } from "./ui";
import { useCooldown } from "../hooks/useCooldown";
import { LoginResult, QrStart, errorText, qrPoll, qrStart } from "../lib/auth";

export const QR_POLL_MS = 2000;
export const QR_INSTRUCTIONS =
  "Mở Mạng xã hội trên điện thoại đã đăng nhập, quét mã này, đối chiếu mã xác nhận rồi bấm Cho phép";

type Phase = "loading" | "active" | "expired" | "denied" | "approved" | "failed" | "error";

interface Props {
  signIn: (action: () => Promise<LoginResult | undefined>) => Promise<void>;
}

const GONE_STATUSES = [404, 410];

/** Đăng nhập bằng mã QR: máy tính hiện mã, điện thoại đã đăng nhập cho phép. Hỏi trạng thái mỗi 2 giây. */
export default function QrLogin({ signIn }: Props) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [request, setRequest] = useState<QrStart | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { left, start } = useCooldown();
  const mountedRef = useRef(true);
  const signInRef = useRef(signIn);

  useEffect(() => {
    signInRef.current = signIn;
  }, [signIn]);

  const create = useCallback(async () => {
    setPhase("loading");
    setError(null);
    setRequest(null);
    try {
      const started = await qrStart();
      if (!mountedRef.current) return;
      setRequest(started);
      setPhase("active");
      start(started.expires_in);
    } catch (caught) {
      if (!mountedRef.current) return;
      setError(errorText(caught));
      setPhase("error");
    }
  }, [start]);

  useEffect(() => {
    mountedRef.current = true;
    void create();
    return () => {
      mountedRef.current = false;
    };
  }, [create]);

  useEffect(() => {
    if (phase === "active" && left <= 0) setPhase("expired");
  }, [phase, left]);

  // One request at a time: the next poll is scheduled only after the previous one finished.
  useEffect(() => {
    if (phase !== "active" || !request) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function tick(current: QrStart) {
      try {
        const result = await qrPoll(current.request_id, current.poll_token);
        if (cancelled) return;
        if (result.kind !== "status") {
          setPhase("approved");
          await signInRef.current(async () => result);
          if (mountedRef.current) setPhase("failed"); // still here: sign-in failed (its error is shown by the form)
          return;
        }
        if (result.status !== "pending") {
          setPhase(result.status);
          return;
        }
      } catch (caught) {
        if (cancelled) return;
        if (caught instanceof ApiError && GONE_STATUSES.includes(caught.status)) {
          setPhase("expired");
          return;
        }
        // Any other failure is transient (network, 429): keep asking until the code expires.
      }
      timer = setTimeout(() => void tick(current), QR_POLL_MS);
    }

    timer = setTimeout(() => void tick(request), QR_POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [phase, request]);

  if (phase === "loading") return <p role="status" className={NOTE}>Đang tạo mã QR...</p>;
  if (phase === "error" || !request) {
    return (
      <div>
        <Alert text={error} />
        <button type="button" onClick={() => void create()} className={`${PRIMARY_BUTTON} mt-2`}>Tạo mã mới</button>
      </div>
    );
  }

  const showCode = phase === "active" || phase === "approved";
  return (
    <div aria-label="Đăng nhập bằng mã QR" className="text-center">
      {showCode && (
        <>
          <QrImage value={request.qr_url} alt="Mã QR để đăng nhập bằng điện thoại"
                   failureText="Không tạo được mã QR, hãy bấm Tạo mã mới." />
          <p className="text-3xl font-mono font-bold tracking-widest my-2">Mã xác nhận: {request.verify_code}</p>
          <p className={NOTE}>{QR_INSTRUCTIONS}</p>
        </>
      )}
      {phase === "active" && <p role="timer" className={NOTE}>Mã hết hạn sau {left} giây</p>}
      {phase === "approved" && <p role="status" className="text-sm text-green-700">Đã được cho phép, đang đăng nhập...</p>}
      {phase === "expired" && <Alert text="Mã QR đã hết hạn" />}
      {phase === "denied" && <Alert text="Yêu cầu đăng nhập đã bị từ chối trên điện thoại" />}
      {!showCode && (
        <button type="button" onClick={() => void create()} className={`${PRIMARY_BUTTON} mt-2`}>Tạo mã mới</button>
      )}
    </div>
  );
}
