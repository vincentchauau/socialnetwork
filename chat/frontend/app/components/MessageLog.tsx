"use client";

import { useLayoutEffect, useMemo, useRef } from "react";

import { ChatMessage, SystemLine, buildTimeline, systemText } from "../protocol";

const BOTTOM_TOLERANCE_PX = 40;

interface Props {
  messages: ChatMessage[];
  system: SystemLine[];
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

/** Plain paragraphs, one per message, like the original #messages div. */
export default function MessageLog({ messages, system }: Props) {
  const items = useMemo(() => buildTimeline(messages, system), [messages, system]);
  const logRef = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);

  function handleScroll() {
    const el = logRef.current;
    if (el) atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_TOLERANCE_PX;
  }

  // Follow new content only when the reader is already at the bottom.
  useLayoutEffect(() => {
    const el = logRef.current;
    if (el && atBottom.current) el.scrollTop = el.scrollHeight;
  }, [items]);

  return (
    <div
      id="messages"
      ref={logRef}
      role="log"
      aria-live="polite"
      aria-relevant="additions"
      aria-label="Tin nhắn"
      tabIndex={0}
      style={{ overflow: "auto" }}
      onScroll={handleScroll}
    >
      {items.length === 0 && <p>Chưa có tin nhắn nào.</p>}
      {items.map((item) =>
        item.kind === "system" ? (
          <p key={item.key} style={{ fontStyle: "italic", lineHeight: 1.5, margin: 0 }}>
            {systemText(item.line)}
          </p>
        ) : (
          <p key={item.key} className="message" style={{ lineHeight: 1.5, margin: 0 }}>
            <b>{item.message.username}</b>{" "}
            <time dateTime={item.message.created_at}>{formatTime(item.message.created_at)}</time>
            {": "}
            <span style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{item.message.content}</span>
          </p>
        ),
      )}
    </div>
  );
}
