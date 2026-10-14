"use client";

import { KeyboardEvent, useEffect, useRef } from "react";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Modal help: focus moves in, Tab is trapped, Escape closes, focus returns to the opener. */
export default function HelpDialog({ onClose }: { onClose: () => void }) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    dialogRef.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    return () => opener?.focus();
  }, []);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const items = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && active === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div className="dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div
        ref={dialogRef}
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="help-title"
        onKeyDown={handleKeyDown}
      >
        <h2 id="help-title">Trợ giúp</h2>
        <ul>
          <li>Gõ tên phòng vào ô đầu tiên để lọc danh sách phòng; bấm Join In để vào (hoặc tạo) phòng đó.</li>
          <li>Ô thứ hai lọc phòng theo tên thành viên đang ở trong phòng.</li>
          <li>Bấm vào một phòng trong danh sách để xem thành viên, bấm Join để vào phòng.</li>
          <li>Join Out để rời phòng hiện tại. Columns chia khung tin nhắn thành 1 đến 6 cột.</li>
          <li>Enter để gửi tin nhắn, Shift+Enter để xuống dòng (tối đa 2000 ký tự).</li>
          <li>Theme đổi màu giao diện, Hide/Show ẩn hoặc hiện phần tiêu đề.</li>
        </ul>
        <button type="button" onClick={onClose}>
          Đóng
        </button>
      </div>
    </div>
  );
}
