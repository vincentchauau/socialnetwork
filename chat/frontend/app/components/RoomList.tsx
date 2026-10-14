"use client";

import { KeyboardEvent, useState } from "react";

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

/** Like the original: clicking a room both expands its member names and enters the room. */
export default function RoomList({ rooms, mode, current, totalRooms, onJoin }: Props) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());

  function open(room: string) {
    const next = new Set(expanded);
    if (!next.delete(room)) next.add(room);
    setExpanded(next);
    onJoin(room);
  }

  function onKey(event: KeyboardEvent, room: string) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    open(room);
  }

  return (
    <div className="maxColumnContainer">
      <h3>Rooms:</h3>
      <p style={{ fontSize: "0.8em", lineHeight: 1.5, margin: "0 0 4px 10px" }}>{MODE_TEXT[mode]}</p>
      {rooms.length === 0 ? (
        <p style={{ marginLeft: 10, lineHeight: 1.5 }}>
          {totalRooms === 0 ? "Chưa có phòng nào đang mở." : "Không có phòng nào khớp bộ lọc."}
        </p>
      ) : (
        <ul id="rooms" aria-label="Danh sách phòng">
          {rooms.map((info) => {
            const isOpen = expanded.has(info.room);
            const hidden = Math.max(0, info.users - info.members.length);
            return (
              <li key={info.room} className={info.room === current ? "selected" : undefined}>
                <span
                  role="button"
                  tabIndex={0}
                  aria-expanded={isOpen}
                  aria-controls={`members-${info.room}`}
                  style={{ cursor: "pointer" }}
                  onClick={() => open(info.room)}
                  onKeyDown={(event) => onKey(event, info.room)}
                >
                  <span>{info.room}</span> <span>{`${info.users} người`}</span>
                </span>
                {isOpen && (
                  <ul id={`members-${info.room}`} aria-label={`Thành viên ${info.room}`}>
                    {info.members.map((name) => (
                      <li key={name}>{name}</li>
                    ))}
                    {hidden > 0 && <li>{`+${hidden} người khác`}</li>}
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
