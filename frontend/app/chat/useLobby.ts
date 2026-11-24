"use client";

import { useEffect, useState } from "react";

import { CLOSE_POLICY, CLOSE_TRY_LATER, backoffDelay, parseFrame, socketUrl } from "./protocol";

export type LobbyMode = "connecting" | "live" | "polling";

interface Lobby {
  /** Who is online now, by room address: the public rooms only (the server names no other). */
  online: ReadonlyMap<string, number>;
  /** Moves on when a room is made, changed or removed: the list is fetched again. */
  version: number;
  /** Moves on when someone comes online or goes away: the list of people is fetched again. */
  people: number;
  /** How many people have the chat open now. */
  onlineTotal: number;
  mode: LobbyMode;
}

/** The live side of the room list, from /ws-lobby. Without the socket the mode says "polling" and the list polls. */
export function useLobby(): Lobby {
  const [online, setOnline] = useState<ReadonlyMap<string, number>>(new Map());
  const [version, setVersion] = useState(0);
  const [people, setPeople] = useState(0);
  const [onlineTotal, setOnlineTotal] = useState(0);
  const [mode, setMode] = useState<LobbyMode>("connecting");

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;

    const connect = () => {
      const ws = new WebSocket(socketUrl("/ws-lobby"));
      socket = ws;
      ws.onopen = () => {
        attempt = 0;
        setMode("live");
      };
      ws.onmessage = (event: MessageEvent) => {
        const frame = parseFrame(event.data);
        if (frame?.type !== "rooms") return;
        setOnline(new Map(frame.rooms.map((room) => [room.room, room.users])));
        setVersion(frame.version);
        setPeople(frame.people);
        setOnlineTotal(frame.online);
      };
      ws.onclose = (event: CloseEvent) => {
        socket = null;
        if (cancelled) return;
        setMode("polling");
        if (event.code === CLOSE_POLICY || event.code === CLOSE_TRY_LATER) return;
        attempt += 1;
        retryTimer = setTimeout(connect, backoffDelay(attempt));
      };
    };

    connect();

    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      if (socket) {
        socket.onopen = socket.onmessage = socket.onclose = null;
        socket.close();
      }
    };
  }, []);

  return { online, version, people, onlineTotal, mode };
}
