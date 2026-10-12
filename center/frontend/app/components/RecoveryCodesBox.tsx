"use client";

import { useState } from "react";

import Alert from "./Alert";
import { PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";

export const RECOVERY_FILE_NAME = "ma-khoi-phuc.txt";

/** Copy text to the clipboard; false when the browser refuses (insecure context, denied permission). */
export async function copyText(text: string): Promise<boolean> {
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
      <button type="button" className={className} onClick={async () => setState((await copyText(text)) ? "ok" : "failed")}>
        {label}
      </button>
      <Alert text={state === "failed" ? "Không sao chép được, hãy chọn và sao chép thủ công" : null} />
      <Alert text={state === "ok" ? "Đã sao chép" : null} ok />
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
    <section aria-label="Mã khôi phục" className="border-2 border-amber-500 bg-amber-50 rounded p-3 mb-2">
      <h3 className="font-bold text-amber-900 mb-1">Lưu ngay các mã khôi phục</h3>
      <p role="note" className="text-sm text-amber-900 mb-2">
        Các mã này chỉ hiển thị một lần và mỗi mã chỉ dùng được một lần. Hãy cất ở nơi an toàn: mất ứng dụng xác thực mà không có mã, bạn có thể bị khóa khỏi tài khoản.
      </p>
      <ul aria-label="Danh sách mã khôi phục" className="grid grid-cols-2 gap-1 font-mono text-sm mb-2">
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ul>
      <div className="flex flex-col gap-2 mb-2">
        <CopyButton text={text} label="Sao chép" />
        <button type="button" className={SECONDARY_BUTTON} onClick={() => downloadText(RECOVERY_FILE_NAME, `${text}\n`)}>
          Tải xuống (.txt)
        </button>
      </div>
      <label className="flex items-center gap-2 text-sm mb-2">
        <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} />
        Tôi đã lưu các mã này
      </label>
      <button type="button" disabled={!saved} onClick={onDismiss} className={PRIMARY_BUTTON}>
        Hoàn tất
      </button>
    </section>
  );
}
