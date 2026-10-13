"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useCommand } from "../hooks/useCommand";
import { useRoom } from "../hooks/useRoom";
import { useToast } from "../hooks/useToast";
import { werewolfApi } from "../lib/api";
import type { RoomState } from "../lib/types";
import Avatar from "./Avatar";
import GameView from "./GameView";
import LobbyView from "./LobbyView";
import Toast from "./Toast";

function Preview({ room, busy, onJoin }: { room: RoomState; busy: boolean; onJoin: () => void }) {
  return (
    <div className="stack">
      <h1>🏕️ {room.title || `Phòng ${room.code}`}</h1>
      <p className="ww-code">🔑 {room.code}</p>
      <section className="card" aria-label="Người trong phòng">
        <h2>👥 {room.members.length} người</h2>
        <ul className="ww-members ww-plain-list">
          {room.members.map((member) => (
            <li key={member.seat} className="ww-member">
              <Avatar name={member.name} size={48} />
              <span className="ww-tile-name">{member.name}</span>
              <span aria-hidden="true">{member.isBot ? "🤖" : ""}</span>
            </li>
          ))}
        </ul>
      </section>
      <button type="button" disabled={busy || room.started} onClick={onJoin}>
        Vào phòng
      </button>
      {room.started && <p className="muted">Ván đã bắt đầu, bạn không thể vào lúc này.</p>}
      <Link href="/">← Danh sách phòng</Link>
    </div>
  );
}

/** One room: loads state, keeps it live over the websocket, and renders preview / lobby / game for it. */
export default function RoomView({ code }: { code: string }) {
  const router = useRouter();
  const { room, status, fatal, frameError, applyEnvelope, applyChat } = useRoom(code);
  const { message, notify, dismiss } = useToast();
  const { busy, run } = useCommand(notify);

  useEffect(() => {
    if (frameError) notify(frameError.text);
  }, [frameError, notify]);

  const envelope = (call: () => ReturnType<typeof werewolfApi.start>) =>
    void run(async () => applyEnvelope(await call()));

  const leave = () =>
    void run(async () => {
      await werewolfApi.leave(code);
      router.push("/");
    });

  const sendChat = async (text: string, target: number): Promise<boolean> => {
    const sent = await run(() => werewolfApi.chat(code, text, target));
    if (!sent) return false;
    applyChat(sent.message);
    return true;
  };

  if (fatal) {
    return (
      <div className="stack">
        <h1>🐺 Ma Sói</h1>
        <p role="alert" className="error">
          {fatal}
        </p>
        <Link href="/">← Danh sách phòng</Link>
      </div>
    );
  }
  if (!room) return <p className="muted">Đang tải phòng…</p>;

  let body;
  if (!room.you) {
    body = <Preview room={room} busy={busy} onJoin={() => envelope(() => werewolfApi.join(code))} />;
  } else if (!room.game) {
    body = (
      <LobbyView
        room={room}
        busy={busy}
        onAddBots={(count) => envelope(() => werewolfApi.addBots(code, count))}
        onStart={() => envelope(() => werewolfApi.start(code))}
        onLeave={leave}
      />
    );
  } else {
    body = (
      <GameView
        room={room}
        game={room.game}
        busy={busy}
        onPick={(target, kind) => envelope(() => werewolfApi.act(code, target, kind))}
        onForce={() => envelope(() => werewolfApi.force(code))}
        onRematch={() => envelope(() => werewolfApi.rematch(code))}
        onReset={() => envelope(() => werewolfApi.reset(code))}
        onLeave={leave}
        onSendChat={sendChat}
      />
    );
  }

  return (
    <>
      {status === "reconnecting" && (
        <p role="status" className="ww-banner">
          ⚠️ Mất kết nối, đang kết nối lại…
        </p>
      )}
      {body}
      <Toast message={message} onClose={dismiss} />
    </>
  );
}
