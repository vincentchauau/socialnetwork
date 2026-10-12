"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ApiError, User, apiFetch, refreshSession } from "@sn/api";
import AuthGate from "../../AuthGate";
import { ChatLine, GameState, appendChat, newerState, parseServerEvent } from "../../game";
import RoomBoard from "../../RoomBoard";

const API = "/api/werewolf";
const POLICY_VIOLATION = 1008;
const MAX_RETRY_DELAY_MS = 15_000;
const ROOM_PATTERN = /^[A-Za-z0-9_-]{1,32}$/;

type Load = { status: "loading" } | { status: "error"; message: string } | { status: "ready" };

function socketUrl(roomId: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${API}/ws/${roomId}`;
}

function Room({ roomId, user }: { roomId: string; user: User }) {
  const router = useRouter();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [game, setGame] = useState<GameState | null>(null);
  const [chat, setChat] = useState<ChatLine[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const lineKey = useRef(0);

  const isMember = game?.you != null;

  useEffect(() => {
    let cancelled = false;
    apiFetch<{ state: GameState }>(`${API}/rooms/${roomId}`)
      .then((room) => {
        if (cancelled) return;
        setGame((current) => newerState(current, room.state));
        setLoad({ status: "ready" });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const message = error instanceof ApiError ? error.message : "Could not load the room";
        setLoad({ status: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [roomId]);

  useEffect(() => {
    if (!isMember) return;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let cancelled = false;
    let refreshed = false; // one session refresh per failed connection, never a loop

    const connect = () => {
      const ws = new WebSocket(socketUrl(roomId));
      socket = ws;
      socketRef.current = ws;
      ws.onopen = () => {
        attempt = 0;
        refreshed = false;
        setConnected(true);
      };
      ws.onmessage = (event: MessageEvent<string>) => {
        const data = parseServerEvent(event.data);
        if (data === null) return;
        if (data.type === "state") {
          setGame((current) => newerState(current, data.state));
          setNotice(null);
        } else if (data.type === "chat") {
          lineKey.current += 1;
          const line: ChatLine = {
            key: lineKey.current,
            scope: data.scope,
            username: data.username,
            content: data.content,
          };
          setChat((current) => appendChat(current, line));
        } else {
          setNotice(data.error);
        }
      };
      ws.onclose = (event: CloseEvent) => {
        setConnected(false);
        if (event.code === POLICY_VIOLATION) {
          const denied = () =>
            setNotice("You are no longer connected to this game. Your session may have expired.");
          if (refreshed) return denied();
          refreshed = true;
          void refreshSession().then((ok) => {
            if (cancelled) return;
            if (ok) connect();
            else denied();
          });
          return;
        }
        attempt += 1;
        retryTimer = setTimeout(connect, Math.min(1000 * 2 ** attempt, MAX_RETRY_DELAY_MS));
      };
    };
    connect();

    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      if (socket) {
        // Detach first so a late onclose cannot touch the next connection's state.
        socket.onopen = socket.onmessage = socket.onclose = null;
        socket.close();
      }
      socketRef.current = null;
      setConnected(false);
    };
  }, [roomId, isMember]);

  function send(message: Record<string, unknown>) {
    const socket = socketRef.current;
    if (socket?.readyState !== WebSocket.OPEN) {
      setNotice("Not connected yet. Please wait a moment.");
      return;
    }
    socket.send(JSON.stringify(message));
  }

  async function post(path: string, onDone?: (state: GameState | null) => void) {
    setBusy(true);
    setNotice(null);
    try {
      const body = await apiFetch<{ state?: GameState }>(`${API}/rooms/${roomId}/${path}`, {
        method: "POST",
      });
      onDone?.(body.state ?? null);
    } catch (error: unknown) {
      setNotice(error instanceof ApiError ? error.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  if (load.status === "loading") return <p className="muted">Loading…</p>;

  if (load.status === "error" || game === null) {
    return (
      <div className="stack">
        <h1>Werewolf</h1>
        <p role="alert" className="error">
          {load.status === "error" ? load.message : "Could not load the room"}
        </p>
        <a href="/werewolf">← Back to lobby</a>
      </div>
    );
  }

  return (
    <RoomBoard
      state={game}
      username={user.username}
      chat={chat}
      connected={connected}
      busy={busy}
      notice={notice}
      onAction={(target) => send({ type: "action", target })}
      onVote={(target) => send({ type: "vote", target })}
      onChat={(content) => send({ type: "chat", content })}
      onAdvance={() => send({ type: "advance" })}
      onStart={() => void post("start", (state) => state && setGame((cur) => newerState(cur, state)))}
      onJoin={() => void post("join", (state) => state && setGame((cur) => newerState(cur, state)))}
      onLeave={() => void post("leave", () => router.push("/"))}
    />
  );
}

export default function RoomPage() {
  const params = useParams<{ id: string }>();
  const roomId = params.id;

  return (
    <AuthGate title="Werewolf">
      {(user) =>
        ROOM_PATTERN.test(roomId) ? (
          <Room key={roomId} roomId={roomId} user={user} />
        ) : (
          <div className="stack">
            <h1>Werewolf</h1>
            <p role="alert" className="error">
              That room link is not valid.
            </p>
            <a href="/werewolf">← Back to lobby</a>
          </div>
        )
      }
    </AuthGate>
  );
}
