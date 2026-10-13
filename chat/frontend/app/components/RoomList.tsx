"use client";

import { FormEvent, useState } from "react";

import type { LobbyMode } from "../useLobby";
import { ROOM_NAME_HINT, RoomInfo, isValidRoom } from "../protocol";

interface Props {
  rooms: RoomInfo[];
  mode: LobbyMode;
  current: string | null;
  onJoin: (room: string) => void;
}

const MODE_TEXT: Record<LobbyMode, string> = {
  connecting: "Đang kết nối…",
  live: "Cập nhật trực tiếp",
  polling: "Cập nhật mỗi 10 giây",
};

export default function RoomList({ rooms, mode, current, onJoin }: Props) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = name.trim();
    if (!isValidRoom(value)) {
      setError(ROOM_NAME_HINT);
      return;
    }
    setError(null);
    setName("");
    onJoin(value);
  }

  return (
    <nav className="room-list stack" aria-label="Phòng chat">
      <h2>Phòng đang mở</h2>
      <p className="muted small">{MODE_TEXT[mode]}</p>

      {rooms.length === 0 ? (
        <p className="muted">Chưa có phòng nào đang mở.</p>
      ) : (
        <>
          <select
            className="room-select"
            aria-label="Chọn phòng"
            value={current !== null && rooms.some((r) => r.room === current) ? current : ""}
            onChange={(event) => event.target.value && onJoin(event.target.value)}
          >
            <option value="">Chọn một phòng…</option>
            {rooms.map((r) => (
              <option key={r.room} value={r.room}>
                {`${r.room} (${r.users})`}
              </option>
            ))}
          </select>
          <ul className="room-items" aria-label="Danh sách phòng">
            {rooms.map((r) => (
              <li key={r.room}>
                <button
                  type="button"
                  className="secondary room-button"
                  aria-current={r.room === current ? "true" : undefined}
                  onClick={() => onJoin(r.room)}
                >
                  <span>{r.room}</span>
                  <span className="muted">{`${r.users} người`}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      <form className="stack" onSubmit={submit} noValidate>
        <label htmlFor="new-room">Tạo hoặc vào phòng</label>
        <div className="row">
          <input
            id="new-room"
            value={name}
            maxLength={32}
            autoComplete="off"
            placeholder="ten-phong"
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "new-room-error" : undefined}
            onChange={(event) => setName(event.target.value)}
          />
          <button type="submit">Vào</button>
        </div>
        {error && (
          <p id="new-room-error" role="alert" className="error">
            {error}
          </p>
        )}
      </form>
    </nav>
  );
}
