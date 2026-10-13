"use client";

import { useEffect, useRef, useState } from "react";

import type { ChatChannel, Game } from "../lib/types";
import Avatar from "./Avatar";

export const CHAT_MAX_LENGTH = 140;
const QUICK_REACTIONS = ["👍", "😱", "🤔", "😂", "🙏", "👀"];

const CHANNEL: Record<ChatChannel, { icon: string; title: string }> = {
  public: { icon: "💬", title: "Thảo luận" },
  wolf: { icon: "🐺", title: "Chat riêng của Sói" },
  dead: { icon: "💀", title: "Chat người chết" },
};

interface Props {
  game: Game;
  /** Resolves true when the message was accepted (so the draft can be cleared). */
  onSend: (text: string, target: number) => Promise<boolean>;
}

/** Chat by channel (public by day, wolves at night, dead). Messages are plain text; quick reactions and "Nghi ai?". */
export default function ChatPanel({ game, onSend }: Props) {
  const [text, setText] = useState("");
  const [suspect, setSuspect] = useState(0);
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLUListElement>(null);
  const channel = game.chatChannel;

  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [game.chat.length]);

  const send = async (body: string, target: number, isDraft: boolean) => {
    const clean = body.trim();
    if (!clean || clean.length > CHAT_MAX_LENGTH || sending) return;
    setSending(true);
    const ok = await onSend(clean, target);
    setSending(false);
    if (ok && isDraft) {
      setText("");
      setSuspect(0);
    }
  };

  const names = new Map(game.players.map((p) => [p.id, p.name]));
  const others = game.players.filter((p) => p.id !== game.me.id && p.alive);
  const title = channel ? CHANNEL[channel].title : "Thảo luận (chưa tới lượt chat)";

  return (
    <section className="card ww-chat" aria-labelledby="ww-chat-title">
      <h2 id="ww-chat-title">
        <span aria-hidden="true">{CHANNEL[channel ?? "public"].icon}</span> {title}
      </h2>
      <ul ref={listRef} className="ww-chat-list" aria-label="Tin nhắn" aria-live="polite">
        {game.chat.length === 0 && <li className="muted">Chưa có tin nhắn nào.</li>}
        {game.chat.map((message) => (
          <li key={message.seq} className="ww-chat-item">
            <Avatar name={message.author.name} size={28} />
            <div>
              <div className={`ww-chat-head${message.author.id === game.me.id ? " ww-me" : ""}`}>
                {message.dead ? "💀 " : ""}
                {message.author.name} <span className="muted">{CHANNEL[message.channel].icon} {message.round}</span>
              </div>
              {/* plain text only: React escapes it, there is no HTML path */}
              <div>
                {message.text}
                {message.target ? <span className="error"> → {names.get(message.target) ?? "?"}</span> : null}
              </div>
            </div>
          </li>
        ))}
      </ul>
      {channel ? (
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            void send(text, suspect, true);
          }}
        >
          <div className="ww-chips" role="group" aria-label="Phản ứng nhanh">
            {QUICK_REACTIONS.map((reaction) => (
              <button
                key={reaction}
                type="button"
                className="secondary ww-chip"
                disabled={sending}
                onClick={() => void send(reaction, 0, false)}
                aria-label={`Gửi ${reaction}`}
              >
                {reaction}
              </button>
            ))}
          </div>
          {channel !== "dead" && (
            <div className="ww-chips" role="group" aria-label="Nghi ai?">
              <button
                type="button"
                className={`ww-chip ${suspect === 0 ? "" : "secondary"}`}
                aria-pressed={suspect === 0}
                onClick={() => setSuspect(0)}
              >
                🤔 Nghi ai?
              </button>
              {others.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`ww-chip ${suspect === p.id ? "" : "secondary"}`}
                  aria-pressed={suspect === p.id}
                  onClick={() => setSuspect(p.id)}
                >
                  {p.name}
                </button>
              ))}
            </div>
          )}
          <div className="row">
            <input
              aria-label="Tin nhắn"
              value={text}
              maxLength={CHAT_MAX_LENGTH}
              placeholder="Nhập tin nhắn…"
              autoComplete="off"
              onChange={(event) => setText(event.target.value)}
            />
            <button type="submit" disabled={sending || !text.trim()}>
              Gửi
            </button>
          </div>
          <span className="muted ww-counter" aria-live="off">
            {text.length}/{CHAT_MAX_LENGTH}
          </span>
        </form>
      ) : (
        <p className="muted">Ban ngày mới chat công khai; ban đêm chỉ Sói có kênh riêng.</p>
      )}
    </section>
  );
}
