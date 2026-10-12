"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { ApiError, CHAT_API, User, apiFetch, loadSession } from "@sn/api";
import { ChatMessage, mergeMessages, parseServerEvent } from "./messages";

type Auth =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "error" }
  | { status: "signed-in"; user: User };

const ROOM_PATTERN = /^[A-Za-z0-9_-]{1,32}$/;
const DEFAULT_ROOM = "general";
const POLICY_VIOLATION = 1008;
const MAX_RETRY_DELAY_MS = 15_000;

function socketUrl(room: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${CHAT_API}/ws/${room}`;
}

export default function ChatPage() {
  const [auth, setAuth] = useState<Auth>({ status: "loading" });
  const [roomInput, setRoomInput] = useState(DEFAULT_ROOM);
  const [room, setRoom] = useState(DEFAULT_ROOM);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [connected, setConnected] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    loadSession()
      .then((user) => setAuth(user ? { status: "signed-in", user } : { status: "anonymous" }))
      .catch(() => setAuth({ status: "error" }));
  }, []);

  const signedIn = auth.status === "signed-in";

  useEffect(() => {
    if (!signedIn) return;
    let cancelled = false;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;

    setMessages([]);
    setNotice(null);

    // Merged by id, so history and live messages can arrive in any order.
    const loadHistory = () =>
      apiFetch<ChatMessage[]>(`${CHAT_API}/rooms/${room}/messages`)
        .then((history) => {
          if (!cancelled) setMessages((current) => mergeMessages(history, current));
        })
        .catch((error: unknown) => {
          if (!cancelled) {
            setNotice(error instanceof ApiError ? error.message : "Could not load history");
          }
        });

    const connect = () => {
      const ws = new WebSocket(socketUrl(room));
      socket = ws;
      socketRef.current = ws;
      ws.onopen = () => {
        attempt = 0;
        setConnected(true);
        void loadHistory(); // catches up on anything missed while disconnected
      };
      ws.onmessage = (event: MessageEvent<string>) => {
        const data = parseServerEvent(event.data);
        if (data === null) return;
        if ("error" in data) {
          setNotice(data.error);
          return;
        }
        setMessages((current) => mergeMessages(current, [data]));
      };
      ws.onclose = (event: CloseEvent) => {
        setConnected(false);
        if (event.code === POLICY_VIOLATION) {
          setNotice("Not allowed to chat here. Your session may have expired — sign in again.");
          return;
        }
        attempt += 1;
        retryTimer = setTimeout(connect, Math.min(1000 * 2 ** attempt, MAX_RETRY_DELAY_MS));
      };
    };

    void loadHistory();
    connect();

    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      if (socket) {
        // Detach first: a late onclose from this socket must not touch the next room's state.
        socket.onopen = socket.onmessage = socket.onclose = null;
        socket.close();
      }
      socketRef.current = null;
      setConnected(false);
    };
  }, [signedIn, room]);

  function joinRoom(event: FormEvent) {
    event.preventDefault();
    if (!ROOM_PATTERN.test(roomInput)) {
      setNotice("Room names use letters, digits, - and _ (max 32)");
      return;
    }
    setRoom(roomInput);
  }

  function send(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    const socket = socketRef.current;
    if (!content || socket?.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ content }));
    setDraft("");
  }

  if (auth.status === "loading") return <p className="muted">Loading…</p>;

  if (auth.status === "error") {
    return (
      <div className="stack">
        <h1>Chat</h1>
        <p role="alert" className="error">
          Could not reach the server. Please try again.
        </p>
      </div>
    );
  }

  if (auth.status === "anonymous") {
    return (
      <div className="stack">
        <h1>Chat</h1>
        <p>
          Please <a href="/login">sign in</a> first.
        </p>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ margin: 0 }}>#{room}</h1>
        <a href="/">← Home</a>
      </div>

      <form className="row" onSubmit={joinRoom}>
        <input
          aria-label="Room"
          value={roomInput}
          onChange={(event) => setRoomInput(event.target.value)}
        />
        <button className="secondary">Join</button>
      </form>

      <p className="muted" aria-live="polite" style={{ margin: 0 }}>
        {connected ? "Connected" : "Connecting…"} as {auth.user.username}
      </p>
      {notice && (
        <p role="alert" className="error">
          {notice}
        </p>
      )}

      <ul className="stack card" style={{ listStyle: "none", margin: 0, minHeight: 240 }}>
        {messages.length === 0 && <li className="muted">No messages yet.</li>}
        {messages.map((message) => (
          <li key={message.id}>
            <strong>{message.username}</strong>{" "}
            <span className="muted">{new Date(message.created_at).toLocaleTimeString()}</span>
            <div style={{ overflowWrap: "anywhere" }}>{message.content}</div>
          </li>
        ))}
      </ul>

      <form className="row" onSubmit={send}>
        <input
          aria-label="Message"
          placeholder="Write a message"
          maxLength={2000}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <button disabled={!connected}>Send</button>
      </form>
    </div>
  );
}
