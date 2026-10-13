"use client";

import { useEffect, useState } from "react";

import { CHAT_API, apiFetch } from "@sn/api";
import {
  CLOSE_POLICY,
  CLOSE_TRY_LATER,
  POLL_INTERVAL_MS,
  RoomInfo,
  backoffDelay,
  parseFrame,
  parseRooms,
  socketUrl,
} from "./protocol";

export type LobbyMode = "connecting" | "live" | "polling";

/** Live room list from /ws-lobby, falling back to polling GET /rooms every 10 s. */
export function useLobby(): { rooms: RoomInfo[]; mode: LobbyMode } {
  const [rooms, setRooms] = useState<RoomInfo[]>([]);
  const [mode, setMode] = useState<LobbyMode>("connecting");

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let pollTimer: ReturnType<typeof setInterval> | undefined;
    let attempt = 0;

    const stopPolling = () => {
      clearInterval(pollTimer);
      pollTimer = undefined;
    };
    const poll = () => {
      apiFetch<unknown>(`${CHAT_API}/rooms`)
        .then((data) => {
          if (!cancelled && pollTimer !== undefined) setRooms(parseRooms(data));
        })
        .catch(() => {
          // keep the last known list; the next tick tries again
        });
    };
    const startPolling = () => {
      if (pollTimer !== undefined) return;
      setMode("polling");
      pollTimer = setInterval(poll, POLL_INTERVAL_MS);
      poll();
    };

    const connect = () => {
      const ws = new WebSocket(socketUrl("/ws-lobby"));
      socket = ws;
      ws.onopen = () => {
        attempt = 0;
        stopPolling();
        setMode("live");
      };
      ws.onmessage = (event: MessageEvent) => {
        const frame = parseFrame(event.data);
        if (frame?.type === "rooms") setRooms(frame.rooms);
      };
      ws.onclose = (event: CloseEvent) => {
        socket = null;
        startPolling();
        if (event.code === CLOSE_POLICY || event.code === CLOSE_TRY_LATER) return;
        attempt += 1;
        retryTimer = setTimeout(connect, backoffDelay(attempt));
      };
    };

    connect();

    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      stopPolling();
      if (socket) {
        socket.onopen = socket.onmessage = socket.onclose = null;
        socket.close();
      }
    };
  }, []);

  return { rooms, mode };
}
