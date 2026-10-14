"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";

import { ROOM_NAME_HINT, filterRooms, isValidRoom } from "../protocol";
import { applyTokens, readStoredTheme, shuffleTheme } from "../theme";
import { useLobby } from "../useLobby";
import NavBar from "./NavBar";
import RoomList from "./RoomList";
import RoomView from "./RoomView";

export const MIN_COLUMNS = 1;
export const MAX_COLUMNS = 6;

const parseColumns = (text: string, fallback: number): number => {
  const value = Math.round(Number(text));
  if (text.trim() === "" || !Number.isFinite(value)) return fallback;
  return Math.min(MAX_COLUMNS, Math.max(MIN_COLUMNS, value));
};

export default function ChatApp({ username }: { username: string }) {
  const [room, setRoom] = useState<string | null>(null);
  const [roomFilter, setRoomFilter] = useState("");
  const [userFilter, setUserFilter] = useState("");
  const [joinError, setJoinError] = useState<string | null>(null);
  const [headerShown, setHeaderShown] = useState(true);
  const [roomsOpen, setRoomsOpen] = useState(true);
  const [columns, setColumns] = useState(1);
  const [columnsText, setColumnsText] = useState("1");
  const { rooms, mode } = useLobby();

  useEffect(() => {
    const stored = readStoredTheme();
    if (stored) applyTokens(stored.tokens);
  }, []);

  const visibleRooms = useMemo(
    () => filterRooms(rooms, roomFilter, userFilter),
    [rooms, roomFilter, userFilter],
  );

  function joinIn(event: FormEvent) {
    event.preventDefault();
    const value = roomFilter.trim();
    if (!isValidRoom(value)) {
      setJoinError(ROOM_NAME_HINT);
      return;
    }
    setJoinError(null);
    setRoomFilter("");
    setRoom(value);
  }

  function joinFromList(name: string) {
    setJoinError(null);
    setRoom(name);
  }

  function changeColumns(event: ChangeEvent<HTMLInputElement>) {
    setColumnsText(event.target.value);
    setColumns(parseColumns(event.target.value, columns));
  }

  return (
    <div className="chat-app">
      <NavBar
        username={username}
        headerShown={headerShown}
        onToggleHeader={() => setHeaderShown(!headerShown)}
        onTheme={() => shuffleTheme()}
      />

      <header id="page-header" className="page-header" hidden={!headerShown}>
        <h1>Chat</h1>
        <p className="muted">Bấm vào một phòng để xem ai đang ở trong đó.</p>
      </header>

      <div className="chat-layout">
        <aside className="rooms-col" aria-label="Phòng chat">
          <button
            type="button"
            className="rooms-toggle"
            aria-expanded={roomsOpen}
            aria-controls="rooms-body"
            onClick={() => setRoomsOpen(!roomsOpen)}
          >
            {roomsOpen ? "Ẩn danh sách phòng" : "Hiện danh sách phòng"}
          </button>
          <div id="rooms-body" className="rooms-body" data-open={roomsOpen}>
            <form className="stack" onSubmit={joinIn} noValidate>
              <input
                type="text"
                value={roomFilter}
                maxLength={32}
                autoComplete="off"
                aria-label="Join or filter by room name..."
                placeholder="Join or filter by room name..."
                aria-invalid={joinError ? true : undefined}
                aria-describedby={joinError ? "join-error" : undefined}
                onChange={(event) => setRoomFilter(event.target.value)}
              />
              <input
                type="text"
                value={userFilter}
                autoComplete="off"
                aria-label="Filter by user name..."
                placeholder="Filter by user name..."
                onChange={(event) => setUserFilter(event.target.value)}
              />
              {joinError && (
                <p id="join-error" role="alert" className="error">
                  {joinError}
                </p>
              )}
              <div className="row">
                <button type="submit">Join In</button>
                <button type="button" disabled={room === null} onClick={() => setRoom(null)}>
                  Join Out
                </button>
              </div>
            </form>
            <RoomList
              rooms={visibleRooms}
              totalRooms={rooms.length}
              mode={mode}
              current={room}
              onJoin={joinFromList}
            />
          </div>
        </aside>

        <section className="chat-main stack" aria-label="Chat">
          <div className="row columns-row">
            <label htmlFor="columns-input">Columns:</label>
            <input
              id="columns-input"
              type="number"
              min={MIN_COLUMNS}
              max={MAX_COLUMNS}
              step={1}
              value={columnsText}
              onChange={changeColumns}
              onBlur={() => setColumnsText(String(columns))}
            />
          </div>
          <h2 className="room-title">{room === null ? "Room:" : `Room: ${room}`}</h2>
          {room === null ? (
            <p className="muted">Chọn một phòng hoặc tạo phòng mới để bắt đầu chat.</p>
          ) : (
            <RoomView key={room} room={room} username={username} columns={columns} />
          )}
        </section>
      </div>
    </div>
  );
}
