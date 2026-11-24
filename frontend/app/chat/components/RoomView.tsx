"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { chatApi } from "../api";
import { errorMessage } from "../errors";
import { type ChatMessage, type Room, isOwner, roomLink, slotsText, stateText } from "../protocol";
import type { Key } from "@sn/compounds/DataTable";
import { type ConnStatus, useRoomChat } from "../useRoomChat";
import AvatarImage from "./AvatarImage";
import RoomStatusControls from "./RoomStatusControls";
import Composer from "./Composer";
import MessageList, { MESSAGE_COLUMNS } from "./MessageList";
import { useColumns } from "./TableControls";
import MessageToolbar from "./MessageToolbar";
import Alert from "@sn/elements/Alert";
import Button from "@sn/elements/Button";
import { ConfirmModal } from "@sn/compounds/Dialogs";
import { tr } from "../i18n";
import { startVoicePlayer, useVoicePlayer } from "../voicePlayer";
import Link from "next/link";

const STATUS_TEXT: Record<ConnStatus, string> = {
  get connecting() { return tr("dang_ket_noi"); },
  get open() { return tr("da_ket_noi"); },
  get reconnecting() { return tr("mat_ket_noi_dang_thu_lai"); },
  get closed() { return tr("da_ngat_ket_noi"); },
};

const READ_DELAY_MS = 800;

interface Props {
  room: Room;
  myId: number;
  /** The name of the signed-in person. */
  username: string;
  /** The room as the server has it now, or null when it is gone for this person (left, deleted). */
  onRoom: (room: Room | null) => void;
  /** Ask for the room (and the list) again. */
  onRefresh: () => void;
  /** Embedded: who has the room open now and how often its people changed, for the members panel of the page around. */
  onLive?: (live: { online: ReadonlySet<number> | undefined; total: number | undefined; version: number }) => void;
}

/** A room someone belongs to: its header, the conversation as a table, and the box to write in. The members are a part of the page around. */
export default function RoomView({ room, myId, username, onRoom, onRefresh, onLive }: Props) {
  const chat = useRoomChat(room.slug);
  const [replyTo, setReplyTo] = useState<ChatMessage | null>(null);
  const [picked, setPicked] = useState<ReadonlySet<Key>>(new Set());
  const [asking, setAsking] = useState(false);
  const [copied, setCopied] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [readUpTo] = useState(room.me?.last_read ?? 0);  // where I had read to when I came (it moves on as I read)
  const messageColumns = useColumns("messages", MESSAGE_COLUMNS);  // what the pane shows: the conversation
  const owner = isOwner(room.me);
  const { roomVersion } = chat;

  // What the virtual people of this room say aloud (a message by voice, a call) is played while the room is open, and its words are shown under the messages.
  useEffect(() => startVoicePlayer(), []);
  const voice = useVoicePlayer();

  // The members or the room changed (the server said so): fetch the room again.
  useEffect(() => {
    if (roomVersion > 0) onRefresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomVersion]);


  // What the reader has seen: the newest message of someone else, once it has been on screen a moment.
  const lastOther = useMemo(() => [...chat.messages].reverse().find((message) => message.user_id !== myId)?.id ?? 0, [chat.messages, myId]);
  useEffect(() => {
    if (!lastOther || chat.status !== "open") return;
    const timer = setTimeout(() => {
      if (document.visibilityState !== "hidden") void chatApi.read(room.slug, lastOther).catch(() => undefined);
    }, READ_DELAY_MS);
    return () => clearTimeout(timer);
  }, [lastOther, chat.status, room.slug]);

  const onlineIds = useMemo(() => (chat.presence ? new Set(chat.presence.members.map((member) => member.userId)) : undefined), [chat.presence]);
  useEffect(() => {
    onLive?.({ online: onlineIds, total: chat.presence?.total, version: roomVersion });
  }, [onLive, onlineIds, roomVersion, chat.presence?.total]);
  const pinned = useMemo(() => [...chat.messages].reverse().find((message) => message.pinned_at), [chat.messages]);

  const blocked =
    chat.stopped !== null || chat.status !== "open"
      ? STATUS_TEXT[chat.status]
      : (stateText(room.state) ?? (room.me?.muted ? tr("rm_ban_dang_bi_tat_tieng") : null));

  async function act(work: () => Promise<unknown>) {
    setProblem(null);
    try {
      await work();
    } catch (caught) {
      setProblem(errorMessage(caught));
    }
  }

  const isOpen = room.state === "open";

  return (
    <section className="cw-pane" aria-label={room.title}>
      <div className="cw-pane-body">
        <div className="cw-chat">
          {chat.status !== "open" && <p role="status" className="cw-notice">{STATUS_TEXT[chat.status]}</p>}
          {chat.notice && <p role="alert" className="cw-notice">{chat.notice}</p>}
          {chat.stopped === "session" && (
            <p className="cw-notice">
              {tr("hay")} <Link href="/user">{tr("dang_nhap")}</Link> {tr("lai_de_tiep_tuc_chat")}
            </p>
          )}
          {chat.stopped === "refused" && (
            <div className="cw-notice"><Button type="button" size="sm" onClick={chat.retry}>{tr("thu_lai")}</Button></div>
          )}
          {chat.stopped === "removed" && (
            <div className="cw-notice"><Button type="button" size="sm" onClick={() => { onRoom(null); onRefresh(); }}>{tr("rm_ve_danh_sach_phong")}</Button></div>
          )}
          {pinned && (
            <div className="cw-pinned" role="note" aria-label={tr("rm_tin_da_ghim")}>
              <b>📌</b>
              <span>{pinned.username}: {pinned.content}</span>
            </div>
          )}
          <MessageToolbar
            slug={room.slug}
            pickedCount={picked.size}
            onDelete={() => setAsking(true)}
            extra={<>
              <RoomStatusControls room={room} onRoom={onRoom} />
              <Button type="button" size="sm" variant="secondary" aria-label={tr("rm_sao_chep_lien_ket_phong")} onClick={() => { void navigator.clipboard?.writeText(roomLink(room.slug)).then(() => setCopied(true), () => setProblem(tr("khong_sao_chep_duoc_hay_chon"))); }}>
            🔗 {copied ? tr("da_sao_chep") : tr("rm_lien_ket")}
          </Button>
              {messageColumns.menu}
            </>}
          />
          <MessageList
            messages={chat.messages}
            system={chat.system}
            myId={myId}
            readUpTo={readUpTo}
            shown={messageColumns.shown}
            hasOlder={chat.hasOlder}
            onLoadOlder={() => void chat.loadOlder()}
            onReply={setReplyTo}
            canModerate={owner}
            onRemove={(message) => {
              setPicked(new Set([message.id]));
              setAsking(true);
            }}
            onPin={(message) => void act(async () => (message.pinned_at ? chatApi.unpin(room.slug, message.id) : chatApi.pin(room.slug, message.id)))}
            onEdit={async (message, content) => {
              setProblem(null);
              try {
                await chatApi.editMessage(room.slug, message.id, content);
              } catch (caught) {
                setProblem(errorMessage(caught));
                throw caught;
              }
            }}
            picked={picked}
            onPicked={setPicked}
            slug={room.slug}
          />
          <Alert>{problem}</Alert>
          {voice.subtitle && (
            <p role="status" aria-live="polite" className="cw-notice" style={{ margin: 0 }}>
              🔊 <b>{voice.subtitle.name}:</b> {voice.subtitle.text}
            </p>
          )}
          <div>
          <Composer
            slug={room.slug}
            blocked={blocked}
            replyTo={replyTo}
            onCancelReply={() => setReplyTo(null)}
            onSend={(content) => {
              const sent = chat.send(content, replyTo?.id);
              if (sent) setReplyTo(null);
              return sent;
            }}
          />
          </div>
        </div>
      </div>
      <ConfirmModal
        open={asking}
        message={tr("rm_xoa_p0_tin_hoi", { p0: picked.size })}
        confirmLabel={tr("rm_xoa")}
        cancelLabel={tr("rm_huy")}
        onCancel={() => setAsking(false)}
        onConfirm={() => {
          const ids = [...picked].filter((key): key is number => typeof key === "number");
          setAsking(false);
          setPicked(new Set());
          void act(async () => {
            for (const id of ids) await chatApi.deleteMessage(room.slug, id);
          });
        }}
      />
    </section>
  );
}
