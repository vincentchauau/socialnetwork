"use client";

import { FormEvent, KeyboardEvent, useState } from "react";

import { MAX_MESSAGE_LENGTH } from "../protocol";

interface Props {
  disabled: boolean;
  onSend: (content: string) => boolean;
}

export default function Composer({ disabled, onSend }: Props) {
  const [draft, setDraft] = useState("");
  const canSend = !disabled && draft.trim().length > 0;

  function submit() {
    const content = draft.trim();
    if (!canSend || content.length > MAX_MESSAGE_LENGTH) return;
    if (onSend(content)) setDraft("");
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    submit();
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <label htmlFor="composer-input" className="sr-only">
        Tin nhắn
      </label>
      <textarea
        id="composer-input"
        rows={2}
        value={draft}
        maxLength={MAX_MESSAGE_LENGTH}
        placeholder="Enter message..."
        aria-describedby="composer-count"
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button type="submit" disabled={!canSend}>
        Send
      </button>
      <span id="composer-count" className="muted small composer-count">
        {`${draft.length}/${MAX_MESSAGE_LENGTH}`}
      </span>
    </form>
  );
}
