"use client";

import { useCallback, useEffect, useState } from "react";

import { chatApi, socialApi } from "../api";
import { errorMessage } from "../errors";
import { type ChatMessage, type Room } from "../protocol";
import MessageList from "./MessageList";
import Alert from "@sn/elements/Alert";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";

const NOTHING = () => undefined;

interface Props {
  room: Room;
  myId: number;
  /** The chat after I said yes (the room as it is now), or null when I said no or blocked: the request is gone. */
  onAnswered: (room: Room | null) => void;
}

/** Someone asked to write to me: what they sent, and the three things I can do (accept, decline, block). */
export default function DmRequest({ room, myId, onAnswered }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const asker = room.title.split(" & ")[0] || room.title;

  const load = useCallback(async () => {
    try {
      setMessages(await chatApi.history(room.slug));
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [room.slug]);

  useEffect(() => {
    void load();
  }, [load]);

  async function answer(work: () => Promise<Room | null>) {
    setBusy(true);
    setError(null);
    try {
      onAnswered(await work());
    } catch (caught) {
      setError(errorMessage(caught));
      setBusy(false);
    }
  }

  return (
    <section className="cw-pane" aria-label={tr("rm_yeu_cau_nhan_tin")}>
      <header className="cw-pane-head">
        <div className="cw-room-text">
          <h2 className="cw-room-title" style={{ margin: 0, fontSize: "1.05rem" }}>{tr("rm_yeu_cau_nhan_tin")}</h2>
        </div>
      </header>
      <div className="cw-pane-body">
        <div className="cw-chat">
          <p role="status" className="cw-notice">{tr("rm_yeu_cau_giai_thich", { p0: asker })}</p>
          <MessageList messages={messages} system={[]} myId={myId} readOnly hasOlder={false} onLoadOlder={NOTHING} onReply={NOTHING} />
          <Alert>{error}</Alert>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", padding: 8 }}>
            <Button type="button" disabled={busy} onClick={() => void answer(() => chatApi.acceptRequest(room.slug))}>{tr("rm_chap_nhan_tro_chuyen")}</Button>
            <Button type="button" variant="secondary" disabled={busy} onClick={() => void answer(async () => { await chatApi.declineRequest(room.slug); return null; })}>{tr("rm_tu_choi_yeu_cau")}</Button>
            <Button
              type="button"
              variant="secondary"
              disabled={busy}
              onClick={() => void answer(async () => { await socialApi.block(room.user_id); await chatApi.declineRequest(room.slug); return null; })}
            >
              {tr("rm_chan_nguoi_nay")}
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
