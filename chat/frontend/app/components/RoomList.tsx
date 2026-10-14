"use client";

import { useState } from "react";

import type { LobbyMode } from "../useLobby";
import { RoomInfo } from "../protocol";

interface Props {
  rooms: RoomInfo[];
  mode: LobbyMode;
  current: string | null;
  totalRooms: number;
  onJoin: (room: string) => void;
}

const MODE_TEXT: Record<LobbyMode, string> = {
  connecting: "Đang kết nối…",
  live: "Cập nhật trực tiếp",
  polling: "Cập nhật mỗi 10 giây",
};

export default function RoomList({ rooms, mode, current, totalRooms, onJoin }: Props) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());

  function toggle(room: string) {
    const next = new Set(expanded);
    if (!next.delete(room)) next.add(room);
    setExpanded(next);
  }

  return (
    <div className="stack">
      <h2>Rooms:</h2>
      <p className="muted small">{MODE_TEXT[mode]}</p>
      {rooms.length === 0 ? (
        <p className="muted">
          {totalRooms === 0 ? "Chưa có phòng nào đang mở." : "Không có phòng nào khớp bộ lọc."}
        </p>
      ) : (
        <ul className="room-items" aria-label="Danh sách phòng">
          {rooms.map((info) => {
            const open = expanded.has(info.room);
            const hidden = Math.max(0, info.users - info.members.length);
            return (
              <li key={info.room} className="room-item" aria-current={info.room === current ? "true" : undefined}>
                <div className="room-row">
                  <button
                    type="button"
                    className="room-toggle"
                    aria-expanded={open}
                    aria-controls={`members-${info.room}`}
                    onClick={() => toggle(info.room)}
                  >
                    <span>{info.room}</span>
                    <span className="muted">{`${info.users} người`}</span>
                  </button>
                  <button
                    type="button"
                    className="room-join"
                    aria-label={`Join ${info.room}`}
                    onClick={() => onJoin(info.room)}
                  >
                    Join
                  </button>
                </div>
                {open && (
                  <ul id={`members-${info.room}`} className="room-members" aria-label={`Thành viên ${info.room}`}>
                    {info.members.map((name) => (
                      <li key={name}>{name}</li>
                    ))}
                    {hidden > 0 && <li className="muted">{`+${hidden} người khác`}</li>}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
