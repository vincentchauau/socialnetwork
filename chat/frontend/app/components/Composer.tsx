"use client";

import { FormEvent, useState } from "react";

import { MAX_MESSAGE_LENGTH } from "../protocol";

interface Props {
  disabled: boolean;
  onSend: (content: string) => boolean;
}

/** One-line message box with a Send button, as in the original. Enter sends. */
export default function Composer({ disabled, onSend }: Props) {
  const [draft, setDraft] = useState("");
  const canSend = !disabled && draft.trim().length > 0;

  function submit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!canSend || content.length > MAX_MESSAGE_LENGTH) return;
    if (onSend(content)) setDraft("");
  }

  return (
    <form className="rowContainer" onSubmit={submit}>
      <label htmlFor="composer-input" className="sr-only">
        Tin nhắn
      </label>
      <input
        id="composer-input"
        type="text"
        autoComplete="off"
        value={draft}
        maxLength={MAX_MESSAGE_LENGTH}
        placeholder="Enter message..."
        onChange={(event) => setDraft(event.target.value)}
      />
      <button type="submit" style={{ flex: 0, width: 50 }} disabled={!canSend}>
        Send
      </button>
    </form>
  );
}
