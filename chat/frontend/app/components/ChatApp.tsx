"use client";

import { useState } from "react";

import { useLobby } from "../useLobby";
import RoomList from "./RoomList";
import RoomView from "./RoomView";

export default function ChatApp({ username }: { username: string }) {
  const [room, setRoom] = useState<string | null>(null);
  const { rooms, mode } = useLobby();

  return (
    <div className="chat-layout">
      <aside>
        <RoomList rooms={rooms} mode={mode} current={room} onJoin={setRoom} />
      </aside>
      <div className="chat-main">
        {room === null ? (
          <p className="muted">Chọn một phòng hoặc tạo phòng mới để bắt đầu chat.</p>
        ) : (
          <RoomView key={room} room={room} username={username} onLeave={() => setRoom(null)} />
        )}
      </div>
    </div>
  );
}
