"use client";

import { ApiError } from "@sn/api";
import { FormEvent, useEffect, useState } from "react";

import Alert from "@sn/elements/Alert";
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
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import Link from "next/link";
import TextBox from "@sn/elements/TextBox";

const VERIFY_CODE_LENGTH = 4;
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
    if (typed.length !== VERIFY_CODE_LENGTH) return fail(tr("hay_nhap_ma_xac_nhan_gom", { VERIFY_CODE_LENGTH }));
    void run(() => settle(() => qrApprove(requestId, typed), { name: "approved" }));
  }

  function deny() {
    if (!requestId) return;
    void run(() => settle(() => qrDeny(requestId), { name: "denied" }));
  }

  return (
    <main className={CARD}>
      <h1 className="text-2xl font-bold mb-4">{tr("dang_nhap_bang_ma_qr")}</h1>
      {stage.name === "loading" && <p role="status" className={NOTE}>{tr("dang_tai")}</p>}
      {stage.name === "invalid" && (
        <>
          <Alert className="mt-2">{tr("lien_ket_khong_hop_le_hay")}</Alert>
          <Link href="/user" className={`${LINK_BUTTON} block text-center`}>{tr("ve_trang_dang_nhap")}</Link>
        </>
      )}
      {stage.name === "signedOut" && (
        <>
          <p role="alert" className="text-sm text-line mb-2">
            {tr("ban_can_dang_nhap_tren_dien")}
          </p>
          <Link href="/user" className={`${PRIMARY_BUTTON} block text-center`}>{tr("dang_nhap")}</Link>
        </>
      )}
      {stage.name === "expired" && (
        <>
          <Alert className="mt-2">{QR_EXPIRED_MESSAGE}</Alert>
          <Link href="/" className={`${LINK_BUTTON} block text-center`}>{tr("ve_trang_chu")}</Link>
        </>
      )}
      {stage.name === "error" && <Alert className="mt-2">{stage.text}</Alert>}
      {stage.name === "approved" && (
        <p role="status" className="text-sm text-line">{tr("da_cho_phep_dang_nhap_tren")}</p>
      )}
      {stage.name === "denied" && <p role="status" className="text-sm text-line">{tr("da_tu_choi_yeu_cau_dang")}</p>}
      {stage.name === "ready" && (
        <form onSubmit={approve} aria-label={tr("cho_phep_dang_nhap")}>
          <section aria-label={tr("thiet_bi_dang_yeu_cau_dang")} className="border rounded p-3 mb-3 text-sm">
            <h2 className="font-bold mb-1">{tr("thiet_bi_dang_yeu_cau_dang")}</h2>
            <p>{describeDevice(stage.request.requester_user_agent)}</p>
            <p>{tr("dia_chi_ip")} {stage.request.requester_ip ?? tr("khong_ro")}</p>
            <p>{tr("luc")} {formatWhen(stage.request.created_at)}</p>
          </section>
          <label htmlFor="qr-verify-code" className={LABEL}>{tr("ma_xac_nhan_hien_thi_tren")}</label>
          <TextBox id="qr-verify-code" value={code} autoComplete="off" autoCapitalize="characters" spellCheck={false}
                 maxLength={VERIFY_CODE_LENGTH} onChange={(e) => setCode(e.target.value.toUpperCase())}
                 className={`${INPUT} text-center text-2xl font-mono tracking-widest`} />
          <p className={NOTE}>{tr("chi_bam_cho_phep_neu_chinh")}</p>
          <Button type="submit" disabled={busy} className={PRIMARY_BUTTON}>{busy ? tr("dang_xu_ly") : tr("cho_phep")}</Button>
          <Button variant="secondary" type="button" disabled={busy} onClick={deny} className={`${SECONDARY_BUTTON} mt-2`}>{tr("tu_choi")}</Button>
          <Alert className="mt-2">{error}</Alert>
        </form>
      )}
    </main>
  );
}
