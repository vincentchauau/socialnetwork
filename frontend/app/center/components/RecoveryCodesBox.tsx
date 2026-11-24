"use client";

import { useState } from "react";

import Alert from "@sn/elements/Alert";
import { PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import CheckBox from "@sn/elements/CheckBox";

const RECOVERY_FILE_NAME = "ma-khoi-phuc.txt";

/** Copy text to the clipboard; false when the browser refuses (insecure context, denied permission). */
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function downloadText(fileName: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

/** Copy button with its own polite confirmation (or a manual-copy hint). */
export function CopyButton({ text, label, className = SECONDARY_BUTTON }: { text: string; label: string; className?: string }) {
  const [state, setState] = useState<"idle" | "ok" | "failed">("idle");
  return (
    <>
      <Button type="button" className={className} onClick={async () => setState((await copyText(text)) ? "ok" : "failed")}>
        {label}
      </Button>
      <Alert className="mt-2">{state === "failed" ? tr("khong_sao_chep_duoc_hay_chon") : null}</Alert>
      <Alert tone="success" className="mt-2">{state === "ok" ? tr("da_sao_chep") : null}</Alert>
    </>
  );
}

interface Props {
  codes: string[];
  onDismiss: () => void;
}

/** Mã khôi phục chỉ hiện MỘT lần: chỉ đóng được sau khi người dùng xác nhận đã lưu. */
export default function RecoveryCodesBox({ codes, onDismiss }: Props) {
  const [saved, setSaved] = useState(false);
  const text = codes.join("\n");

  return (
    <section aria-label={tr("ma_khoi_phuc")} className="border-2 border-line bg-solid rounded p-3 mb-2">
      <h3 className="font-bold text-line mb-1">{tr("luu_ngay_cac_ma_khoi_phuc")}</h3>
      <p role="note" className="text-sm text-line mb-2">
        {tr("cac_ma_nay_chi_hien_thi")}
      </p>
      <ul aria-label={tr("danh_sach_ma_khoi_phuc")} className="grid grid-cols-2 gap-1 font-mono text-sm mb-2">
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ul>
      <div className="flex flex-col gap-2 mb-2">
        <CopyButton text={text} label={tr("sao_chep")} />
        <Button variant="secondary" type="button" className={SECONDARY_BUTTON} onClick={() => downloadText(RECOVERY_FILE_NAME, `${text}\n`)}>
          {tr("tai_xuong_txt")}
        </Button>
      </div>
      <label className="flex items-center gap-2 text-sm mb-2">
        <CheckBox checked={saved} onChange={setSaved} />
        {tr("toi_da_luu_cac_ma_nay")}
      </label>
      <Button type="button" disabled={!saved} onClick={onDismiss} className={PRIMARY_BUTTON}>
        {tr("hoan_tat")}
      </Button>
    </section>
  );
}
