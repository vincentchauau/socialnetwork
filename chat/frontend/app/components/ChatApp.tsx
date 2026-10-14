"use client";

import { useEffect, useMemo, useState } from "react";

import { ROOM_NAME_HINT, filterRooms, isValidRoom } from "../protocol";
import { shuffleTheme } from "../theme";
import { useLobby } from "../useLobby";
import NavBar from "./NavBar";
import RoomList from "./RoomList";
import RoomView, { ColumnsControl, IdleView } from "./RoomView";
import Split from "./Split";

export const MIN_COLUMNS = 1;
export const MAX_COLUMNS = 10;

const parseColumns = (text: string, fallback: number): number => {
  const value = Math.round(Number(text));
  if (text.trim() === "" || !Number.isFinite(value)) return fallback;
  return Math.min(MAX_COLUMNS, Math.max(MIN_COLUMNS, value));
};

/** Same blurb in the header and the footer, which Hide/Show toggles together. */
function Banner({ id }: { id: string }) {
  return (
    <header id={id} style={{ textAlign: "center" }}>
      <p>Chat · bấm vào một phòng để xem ai đang ở trong đó.</p>
    </header>
  );
}

export default function ChatApp({ username }: { username: string }) {
  const [room, setRoom] = useState<string | null>(null);
  const [roomFilter, setRoomFilter] = useState("");
  const [userFilter, setUserFilter] = useState("");
  const [joinError, setJoinError] = useState<string | null>(null);
  const [headerShown, setHeaderShown] = useState(false);
  const [columns, setColumns] = useState(1);
  const [columnsText, setColumnsText] = useState("1");
  const { rooms, mode } = useLobby();

  // The original picks a random colour theme on every load and starts with the header hidden.
  useEffect(() => {
    shuffleTheme();
  }, []);

  const visibleRooms = useMemo(
    () => filterRooms(rooms, roomFilter, userFilter),
    [rooms, roomFilter, userFilter],
  );

  function joinIn() {
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

  const control: ColumnsControl = {
    text: columnsText,
    onChange: (text) => {
      setColumnsText(text);
      setColumns(parseColumns(text, columns));
    },
    onBlur: () => setColumnsText(String(columns)),
  };

  const left = (
    <>
      <div className="columnContainer">
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
          onKeyDown={(event) => event.key === "Enter" && joinIn()}
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
          <p id="join-error" role="alert" style={{ margin: 0 }}>
            {joinError}
          </p>
        )}
        <div className="rowContainer">
          <button type="button" onClick={joinIn}>
            Join In
          </button>
          <button type="button" disabled={room === null} onClick={() => setRoom(null)}>
            Join Out
          </button>
        </div>
      </div>
      <RoomList rooms={visibleRooms} totalRooms={rooms.length} mode={mode} current={room} onJoin={joinFromList} />
    </>
  );

  const right =
    room === null ? (
      <IdleView columns={columns} control={control} />
    ) : (
      <RoomView key={room} room={room} columns={columns} control={control} />
    );

  return (
    <>
      {headerShown && <Banner id="page-header" />}
      <main className="maxColumnContainer">
        <NavBar
          username={username}
          headerShown={headerShown}
          onToggleHeader={() => setHeaderShown(!headerShown)}
          onTheme={() => shuffleTheme()}
        />
        <Split
          id="roomSplitter"
          direction="horizontal"
          percent={30}
          containerClass="fullRowContainer"
          firstClass="columnContainer"
          secondClass="columnContainer"
          first={left}
          second={right}
        />
      </main>
      {headerShown && <Banner id="page-footer" />}
    </>
  );
}
