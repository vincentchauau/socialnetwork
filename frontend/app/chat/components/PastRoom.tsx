"use client";

import { useCallback, useEffect, useState } from "react";

import { HISTORY_PAGE, type ChatMessage, type Room, mergeMessages, stateText } from "../protocol";
import { chatApi } from "../api";
import { errorMessage } from "../errors";
import MessageList from "./MessageList";
import Alert from "@sn/elements/Alert";
import Button from "@sn/elements/Button";
import TextBox from "@sn/elements/TextBox";
import { ConfirmModal } from "@sn/compounds/Dialogs";
import { tr } from "../i18n";

interface Props {
  room: Room;
  myId: number;
  /** The room as the server has it after joining it again or restoring it. */
  onChanged: (room: Room) => void;
  /** The room is gone from my list (removed for good, or taken off it). */
  onGone: () => void;
}

const NOTHING = () => undefined;

/** A room I am no longer in (left, sent out) or that I deleted: its old messages to read, and the way back. */
export default function PastRoom({ room, myId, onChanged, onGone }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hasOlder, setHasOlder] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const deleted = room.state === "deleted";
  const status = room.me?.status;
  const unavailable = deleted ? null : stateText(room.state);

  const load = useCallback(
    async (before?: number) => {
      try {
        const page = await chatApi.history(room.slug, before);
        setMessages((current) => mergeMessages(current, page));
        if (before === undefined || page.length > 0) setHasOlder(page.length >= HISTORY_PAGE);
        else setHasOlder(false);
        setError(null);
      } catch (caught) {
        setError(errorMessage(caught));
      }
    },
    [room.slug],
  );

  useEffect(() => {
    setMessages([]);
    void load();
  }, [load]);

  async function come(work: () => Promise<Room>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      onChanged(await work());
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function hide() {
    setBusy(true);
    try {
      await chatApi.hide(room.slug);
      onGone();
    } catch (caught) {
      setError(errorMessage(caught));
      setBusy(false);
    }
  }

  const banner = deleted ? tr("rm_past_deleted") : status === "kicked" ? tr("rm_past_kicked") : tr("rm_past_left");

  return (
    <section className="cw-pane" aria-label={room.title}>
      <header className="cw-pane-head">
        <div className="cw-room-text">
          <h2 className="cw-room-title" style={{ margin: 0, fontSize: "1.05rem" }}>
            {room.visibility === "private" ? "🔒 " : ""}
            {room.title}
          </h2>
          <span className="cw-room-sub">{room.category}</span>
        </div>
      </header>
      <div className="cw-pane-body">
        <div className="cw-chat">
          <p role="status" className="cw-notice">{banner}</p>
          {unavailable && <p role="status" className="cw-notice">{unavailable}</p>}
          <MessageList
            messages={messages}
            system={[]}
            myId={myId}
            readOnly
            hasOlder={hasOlder}
            onLoadOlder={() => void load(messages[0]?.id)}
            onReply={NOTHING}
          />
          <Alert>{error}</Alert>
          <div className="cw-composer-off" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", padding: 8 }}>
            {!deleted && (status === "left" || status === "kicked") && (
              <Button type="button" variant="secondary" disabled={busy} onClick={() => void hide()}>
                {tr("rm_xoa_khoi_danh_sach")}
              </Button>
            )}
            {deleted ? (
              <>
                <Button type="button" loading={busy} loadingLabel={tr("dang_xu_ly")} onClick={() => void come(() => chatApi.update(room.slug, { state: "open" }))}>
                  {tr("rm_khoi_phuc_phong")}
                </Button>
                <Button type="button" variant="danger" disabled={busy} onClick={() => setConfirmPurge(true)}>
                  {tr("rm_xoa_vinh_vien")}
                </Button>
              </>
            ) : status === "banned" || unavailable ? null : (
              <>
                <Button type="button" loading={busy} loadingLabel={tr("dang_xu_ly")} onClick={() => void come(() => chatApi.join(room.slug))}>
                  {tr("rm_vao_lai_phong")}
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
      <ConfirmModal
        open={confirmPurge}
        message={tr("rm_xoa_vinh_vien_p0_hoi", { p0: room.title })}
        confirmLabel={tr("rm_xoa_vinh_vien")}
        cancelLabel={tr("rm_huy")}
        onCancel={() => setConfirmPurge(false)}
        onConfirm={() => {
          setConfirmPurge(false);
          setBusy(true);
          chatApi.remove(room.slug, true).then(onGone, (caught) => setError(errorMessage(caught))).finally(() => setBusy(false));
        }}
      />
    </section>
  );
}
