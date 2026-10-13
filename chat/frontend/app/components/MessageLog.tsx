"use client";

import { useLayoutEffect, useMemo, useRef } from "react";

import { ChatMessage, SystemLine, buildTimeline, systemText } from "../protocol";

const BOTTOM_TOLERANCE_PX = 40;

interface Props {
  messages: ChatMessage[];
  system: SystemLine[];
  username: string;
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

export default function MessageLog({ messages, system, username }: Props) {
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
      ref={logRef}
      className="message-log"
      role="log"
      aria-live="polite"
      aria-relevant="additions"
      aria-label="Tin nhắn"
      tabIndex={0}
      onScroll={handleScroll}
    >
      {items.length === 0 && <p className="muted">Chưa có tin nhắn nào.</p>}
      {items.map((item) =>
        item.kind === "system" ? (
          <p key={item.key} className="system-line">
            {systemText(item.line)}
          </p>
        ) : (
          <article
            key={item.key}
            className={item.message.username === username ? "bubble own" : "bubble"}
          >
            <header>
              <strong>{item.message.username}</strong>
              <time dateTime={item.message.created_at} className="muted small">
                {formatTime(item.message.created_at)}
              </time>
            </header>
            <div className="bubble-text">{item.message.content}</div>
          </article>
        ),
      )}
    </div>
  );
}
