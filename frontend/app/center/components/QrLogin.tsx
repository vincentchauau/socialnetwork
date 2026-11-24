"use client";

import { ApiError } from "@sn/api";
import { useCallback, useEffect, useRef, useState } from "react";

import Alert from "@sn/elements/Alert";
import QrImage from "./QrImage";
import { NOTE, PRIMARY_BUTTON } from "./ui";
import { useCooldown } from "../hooks/useCooldown";
import { LoginResult, QrStart, errorText, qrPoll, qrStart } from "../lib/auth";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";

export const QR_POLL_MS = 2000;
const QR_INSTRUCTIONS =
  tr("mo_mang_xa_hoi_tren_dien");

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

  if (phase === "loading") return <p role="status" className={NOTE}>{tr("dang_tao_ma_qr")}</p>;
  if (phase === "error" || !request) {
    return (
      <div>
        <Alert className="mt-2">{error}</Alert>
        <Button type="button" onClick={() => void create()} className={`${PRIMARY_BUTTON} mt-2`}>{tr("tao_ma_moi")}</Button>
      </div>
    );
  }

  const showCode = phase === "active" || phase === "approved";
  return (
    <div aria-label={tr("dang_nhap_bang_ma_qr")} className="text-center">
      {showCode && (
        <>
          <QrImage value={request.qr_url} alt={tr("ma_qr_de_dang_nhap_bang")}
                   failureText={tr("khong_tao_duoc_ma_qr_hay")} />
          <p className="text-3xl font-mono font-bold tracking-widest my-2">{tr("ma_xac_nhan")} {request.verify_code}</p>
          <p className={NOTE}>{QR_INSTRUCTIONS}</p>
        </>
      )}
      {phase === "active" && <p role="timer" className={NOTE}>{tr("ma_het_han_sau")} {left} {tr("giay")}</p>}
      {phase === "approved" && <p role="status" className="text-sm text-line">{tr("da_duoc_cho_phep_dang_dang")}</p>}
      {phase === "expired" && <Alert className="mt-2">{tr("ma_qr_da_het_han")}</Alert>}
      {phase === "denied" && <Alert className="mt-2">{tr("yeu_cau_dang_nhap_da_bi")}</Alert>}
      {!showCode && (
        <Button type="button" onClick={() => void create()} className={`${PRIMARY_BUTTON} mt-2`}>{tr("tao_ma_moi")}</Button>
      )}
    </div>
  );
}
