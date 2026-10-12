"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ApiError, apiFetch } from "@sn/api";
import AuthGate from "./AuthGate";
import { RoomSummary } from "./game";

const API = "/api/werewolf";
const REFRESH_MS = 5000;

function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function Lobby({ username }: { username: string }) {
  const router = useRouter();
  const [rooms, setRooms] = useState<RoomSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    apiFetch<RoomSummary[]>(`${API}/rooms`)
      .then((list) => {
        setRooms(list);
        setError(null);
      })
      .catch((e: unknown) => setError(errorText(e, "Could not load rooms")));
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  async function enter(path: string, id?: string) {
    setBusy(true);
    setError(null);
    try {
      const room = await apiFetch<{ id: string }>(path, { method: "POST" });
      router.push(`/room/${encodeURIComponent(id ?? room.id)}`);
    } catch (e: unknown) {
      setError(errorText(e, "Something went wrong"));
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ margin: 0 }}>Werewolf</h1>
        <a href="/">← Home</a>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        Signed in as {username}. Games need 5 to 12 players.
      </p>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      <div className="row" style={{ flexWrap: "wrap" }}>
        <button disabled={busy} onClick={() => enter(`${API}/rooms`)}>
          Create a room
        </button>
        <Link href="/history">My game history</Link>
      </div>

      <h2 style={{ fontSize: "1.1rem", margin: 0 }}>Open rooms</h2>
      {rooms === null && !error && <p className="muted">Loading…</p>}
      {rooms !== null && rooms.length === 0 && (
        <p className="muted">No open rooms yet. Create one and invite friends.</p>
      )}
      <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {rooms?.map((room) => (
          <li
            key={room.id}
            className="card row"
            style={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap" }}
          >
            <span style={{ overflowWrap: "anywhere" }}>
              <strong>{room.host}</strong>&apos;s room{" "}
              <span className="muted">
                {room.players}/{room.max_players} players
              </span>
            </span>
            <button
              className="secondary"
              disabled={busy}
              aria-label={`Join ${room.host}'s room`}
              onClick={() =>
                enter(`${API}/rooms/${encodeURIComponent(room.id)}/join`, room.id)
              }
            >
              Join
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function WerewolfLobbyPage() {
  return <AuthGate title="Werewolf">{(user) => <Lobby username={user.username} />}</AuthGate>;
}
