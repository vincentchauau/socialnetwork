"use client";

import { useEffect } from "react";

import { useCommand } from "../hooks/useCommand";
import { useRoom } from "../hooks/useRoom";
import { useToast } from "../hooks/useToast";
import { werewolfApi } from "../lib/api";
import type { RoomState } from "../lib/types";
import Avatar from "./Avatar";
import GameView from "./GameView";
import LobbyView from "./LobbyView";
import { Toast } from "./Notices";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";

function Preview({ room, busy, onJoin, onExit }: { room: RoomState; busy: boolean; onJoin: () => void; onExit: () => void }) {
  return (
    <div className="stack">
      <h1>🏕️ {room.title || tr("phong_p0", { p0: room.code })}</h1>
      <p className="ww-code">🔑 {room.code}</p>
      <section className="card" aria-label={tr("nguoi_trong_phong")}>
        <h2>👥 {room.members.length} {tr("nguoi")}</h2>
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
      <Button type="button" disabled={busy || room.started} onClick={onJoin}>
        {tr("vao_phong")}
      </Button>
      {room.started && <p className="muted">{tr("van_da_bat_dau_ban_khong")}</p>}
      <Button type="button" variant="ghost" onClick={onExit}>{tr("ww_danh_sach_phong")}</Button>
    </div>
  );
}

/**
 * One room: loads state, keeps it live over the websocket, and renders preview / lobby / game for it. `onExit` takes the person
 * out of it (to the list of rooms, or back to the chat the game is in): after leaving, and from the buttons that say so.
 */
export default function RoomView({ code, onExit, hideRules = false }: { code: string; onExit: () => void; hideRules?: boolean }) {
  const { room, status, fatal, frameError, applyEnvelope } = useRoom(code);
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
      onExit();
    });

  if (fatal) {
    return (
      <div className="stack">
        <h1>{tr("ma_soi_2")}</h1>
        <p role="alert" className="error">
          {fatal}
        </p>
        <Button type="button" variant="ghost" onClick={onExit}>{tr("ww_danh_sach_phong")}</Button>
      </div>
    );
  }
  if (!room) return <p className="muted">{tr("dang_tai_phong")}</p>;

  let body;
  if (!room.you) {
    body = <Preview room={room} busy={busy} onJoin={() => envelope(() => werewolfApi.join(code))} onExit={onExit} />;
  } else if (!room.game) {
    body = (
      <LobbyView
        room={room}
        busy={busy}
        onStart={() => envelope(() => werewolfApi.start(code))}
        onRoles={(body) => envelope(() => werewolfApi.roles(code, body))}
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
      />
    );
  }

  return (
    <>
      {status === "reconnecting" && (
        <p role="status" className="ww-banner">
          {tr("mat_ket_noi_dang_ket_noi")}
        </p>
      )}
      {body}
      <Toast message={message} onClose={dismiss} />
    </>
  );
}
