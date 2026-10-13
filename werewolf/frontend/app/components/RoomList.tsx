"use client";

import { useCallback, useEffect, useState } from "react";

import { werewolfApi } from "../lib/api";
import { errorText } from "../lib/errors";
import type { RoomSummary } from "../lib/types";

export const ROOMS_REFRESH_MS = 5_000;

interface Props {
  busy: boolean;
  onJoin: (code: string) => void;
}

/** Public lobbies with a free seat (GET /rooms), refreshed every few seconds. */
export default function RoomList({ busy, onJoin }: Props) {
  const [rooms, setRooms] = useState<RoomSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    werewolfApi
      .rooms()
      .then((list) => {
        setRooms(list);
        setError(null);
      })
      .catch((e: unknown) => setError(errorText(e)));
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, ROOMS_REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <section className="card stack" aria-labelledby="ww-rooms-title">
      <div className="row ww-between">
        <h2 id="ww-rooms-title">🏘️ Phòng đang mở</h2>
        <button type="button" className="secondary" onClick={refresh} aria-label="Làm mới danh sách phòng">
          ↻
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {rooms === null && !error && <p className="muted">Đang tải…</p>}
      {rooms?.length === 0 && <p className="muted">Chưa có phòng công khai nào. Hãy tạo một phòng!</p>}
      <ul className="ww-plain-list stack">
        {rooms?.map((room) => (
          <li key={room.id} className="ww-room row ww-between">
            <div>
              <strong>{room.title}</strong> <span className="muted">· {room.id}</span>
              <div className="muted">
                👑 {room.host} · 👥 {room.players}/{room.seats} · còn {room.open_seats} ghế
                {room.timer ? ` · ⏱ ${room.timer}s` : ""}
                {room.events ? " · 🎴" : ""}
              </div>
            </div>
            <button type="button" disabled={busy} onClick={() => onJoin(room.id)} aria-label={`Vào phòng ${room.title} (${room.id})`}>
              Vào
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
