"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@sn/api";

import { werewolfApi } from "../lib/api";
import { errorText, frameErrorText } from "../lib/errors";
import {
  CLOSE_GONE,
  CLOSE_POLICY,
  mergeChat,
  parseFrame,
  retryDelay,
  sanitizeRoom,
  socketUrl,
} from "../lib/roomSocket";
import type { ChatMessage, RoomEnvelope, RoomState } from "../lib/types";

export type SocketStatus = "loading" | "connecting" | "open" | "reconnecting" | "closed";

/** A socket closed with 1008 this quickly (or never opened) is a refusal, not a network drop. */
const RAPID_CLOSE_MS = 3_000;
const MAX_RAPID_REFUSALS = 2;
const SOCKET_OPEN = 1;
const FATAL_STATUSES = new Set([401, 403, 404]);

export interface RoomConnection {
  room: RoomState | null;
  status: SocketStatus;
  /** Set when the room can no longer be used (gone, no access, refused): show it and offer a way out. */
  fatal: string | null;
  /** Last error frame sent by the server (a rejected command); `id` changes for every frame. */
  frameError: { id: number; text: string } | null;
  applyEnvelope: (envelope: RoomEnvelope) => void;
  applyChat: (message: ChatMessage) => void;
  refetch: () => Promise<boolean>;
}

/** Room state from REST, then kept fresh by the websocket; reconnects with backoff and re-fetches after a drop. */
export function useRoom(code: string): RoomConnection {
  const [room, setRoom] = useState<RoomState | null>(null);
  const [status, setStatus] = useState<SocketStatus>("loading");
  const [fatal, setFatal] = useState<string | null>(null);
  const [frameError, setFrameError] = useState<{ id: number; text: string } | null>(null);
  const frameCounter = useRef(0);
  const disposedRef = useRef(false);

  /** Re-reads the room over REST. Resolves false when the room can no longer be used (then `fatal` is set). */
  const refetch = useCallback(async (): Promise<boolean> => {
    try {
      const envelope = await werewolfApi.room(code);
      if (!disposedRef.current) setRoom(sanitizeRoom(envelope.state));
      return true;
    } catch (error) {
      if (disposedRef.current) return false;
      if (error instanceof ApiError && FATAL_STATUSES.has(error.status)) {
        setFatal(errorText(error));
        setStatus("closed");
        return false;
      }
      return true; // network/5xx: keep what we have, the reconnect loop tries again
    }
  }, [code]);

  useEffect(() => {
    disposedRef.current = false;
    setRoom(null);
    setFatal(null);
    setStatus("loading");
    void refetch();
    return () => {
      disposedRef.current = true;
    };
  }, [code, refetch]);

  const isMember = room?.you != null;

  useEffect(() => {
    if (!isMember) return undefined;
    let disposed = false;
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let refusals = 0;
    let openedAt: number | null = null;
    let reconnecting = false;

    const giveUp = (text: string) => {
      setFatal(text);
      setStatus("closed");
    };

    const scheduleRetry = () => {
      timer = setTimeout(connect, retryDelay(attempt));
      attempt += 1;
    };

    const handleClose = async (closeCode: number) => {
      if (closeCode === CLOSE_GONE) {
        giveUp("Phòng đã bị xoá.");
        return;
      }
      setStatus("reconnecting");
      reconnecting = true;
      if (closeCode === CLOSE_POLICY) {
        const quick = openedAt === null || Date.now() - openedAt < RAPID_CLOSE_MS;
        refusals = quick ? refusals + 1 : 0;
        if (refusals >= MAX_RAPID_REFUSALS) {
          giveUp("Kết nối bị từ chối. Bạn có thể đang mở phòng này ở một tab khác.");
          return;
        }
      }
      const usable = await refetch(); // also renews an expired session through the shared client
      if (usable && !disposed) scheduleRetry();
    };

    function connect() {
      if (disposed) return;
      openedAt = null;
      const ws = new WebSocket(socketUrl(code));
      socket = ws;
      setStatus(reconnecting ? "reconnecting" : "connecting");
      ws.onopen = () => {
        if (disposed) return;
        openedAt = Date.now();
        attempt = 0;
        setStatus("open");
        if (reconnecting) {
          reconnecting = false;
          void refetch();
        }
      };
      ws.onmessage = (event: MessageEvent) => {
        if (disposed) return;
        const frame = parseFrame(event.data);
        if (!frame) return;
        if (frame.type === "state") setRoom(frame.state);
        else if (frame.type === "chat") setRoom((current) => (current ? mergeChat(current, frame.message) : current));
        else {
          frameCounter.current += 1;
          setFrameError({ id: frameCounter.current, text: frameErrorText(frame.error) });
        }
      };
      ws.onclose = (event: CloseEvent) => {
        if (disposed || socket !== ws) return;
        socket = null;
        void handleClose(event.code);
      };
    }

    connect();
    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
      if (socket && socket.readyState <= SOCKET_OPEN) socket.close();
      socket = null;
    };
  }, [isMember, code, refetch]);

  const applyEnvelope = useCallback((envelope: RoomEnvelope) => setRoom(sanitizeRoom(envelope.state)), []);
  const applyChat = useCallback(
    (message: ChatMessage) => setRoom((current) => (current ? mergeChat(current, message) : current)),
    [],
  );

  return { room, status, fatal, frameError, applyEnvelope, applyChat, refetch };
}
