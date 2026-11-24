"use client";

import { FormEvent, KeyboardEvent, useState } from "react";

import { type ChatMessage, MAX_MESSAGE_LENGTH } from "../protocol";
import Button from "@sn/elements/Button";
import TextBox from "@sn/elements/TextBox";
import { tr } from "../i18n";
import VoiceButton from "./VoiceButton";

interface Props {
  /** The room: a message said aloud is sent to it. */
  slug: string;
  /** Why nothing can be sent now (not connected, muted, closed…); null when it can. */
  blocked: string | null;
  replyTo: ChatMessage | null;
  onCancelReply: () => void;
  onSend: (content: string) => boolean;
}

/** The message box: Enter sends, Shift+Enter starts a new line, and a message being answered shows above it. */
export default function Composer({ slug, blocked, replyTo, onCancelReply, onSend }: Props) {
  const [draft, setDraft] = useState("");
  const canSend = blocked === null && draft.trim().length > 0;

  function send() {
    const content = draft.trim();
    if (!canSend || content.length > MAX_MESSAGE_LENGTH) return;
    if (onSend(content)) setDraft("");
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    send();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  }

  return (
    <form className="cw-composer" onSubmit={submit}>
      {replyTo && (
        <div className="cw-replying">
          <span>{tr("rm_dang_tra_loi_p0", { p0: replyTo.username })}: {replyTo.content}</span>
          <Button type="button" variant="ghost" size="sm" aria-label={tr("rm_huy")} onClick={onCancelReply}>×</Button>
        </div>
      )}
      {blocked && <p role="status" className="cw-room-sub" style={{ margin: 0 }}>{blocked}</p>}
      <div className="cw-composer-row">
        <label htmlFor="composer-input" className="sr-only">{tr("tin_nhan")}</label>
        <TextBox
          id="composer-input"
          multiline
          rows={1}
          autoComplete="off"
          value={draft}
          maxLength={MAX_MESSAGE_LENGTH}
          disabled={blocked !== null}
          placeholder={tr("rm_nhap_tin_nhan")}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <VoiceButton slug={slug} disabled={blocked !== null} />
      </div>
    </form>
  );
}
