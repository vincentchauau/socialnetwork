"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { CHAT_API, apiFetch, refreshSession } from "@sn/api";
import {
  ChatMessage,
  MAX_SYSTEM_LINES,
  Presence,
  SystemLine,
  backoffDelay,
  describeClose,
  mergeMessages,
  parseFrame,
  parseHistory,
  socketUrl,
  translateServerError,
} from "./protocol";

export type ConnStatus = "connecting" | "open" | "reconnecting" | "closed";
export type StopReason = "session" | "refused" | null;

export interface RoomChat {
  messages: ChatMessage[];
  system: SystemLine[];
  presence: Presence | null;
  status: ConnStatus;
  notice: string | null;
  stopped: StopReason;
  send: (content: string) => boolean;
  retry: () => void;
}

/** History (REST) + live frames (/ws/{room}) of one room, with reconnect and cleanup. */
export function useRoomChat(room: string): RoomChat {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [system, setSystem] = useState<SystemLine[]>([]);
  const [presence, setPresence] = useState<Presence | null>(null);
  const [status, setStatus] = useState<ConnStatus>("connecting");
  const [notice, setNotice] = useState<string | null>(null);
  const [stopped, setStopped] = useState<StopReason>(null);
  const [attemptToken, setAttemptToken] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);
  const lineSeq = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let refreshed = false; // one session refresh per failed connection, never a loop

    setStopped(null);
    setStatus("connecting");

    // Merged by id, so history and live messages can arrive in any order.
    const loadHistory = () =>
      apiFetch<unknown>(`${CHAT_API}/rooms/${room}/messages`)
        .then((data) => {
          if (!cancelled) setMessages((current) => mergeMessages(parseHistory(data), current));
        })
        .catch(() => {
          if (!cancelled) setNotice("Không tải được lịch sử tin nhắn.");
        });

    const stop = (reason: StopReason, message: string | null) => {
      setStopped(reason);
      setStatus("closed");
      if (message) setNotice(message);
    };

    const handleClose = (event: CloseEvent) => {
      socket = null;
      socketRef.current = null;
      setPresence(null);
      const info = describeClose(event.code, event.reason);
      if (info.action === "session") {
        if (refreshed) return stop("session", info.message);
        refreshed = true;
        setStatus("reconnecting");
        void refreshSession().then((ok) => {
          if (cancelled) return;
          if (ok) connect();
          else stop("session", info.message);
        });
        return;
      }
      if (info.action === "stop") return stop("refused", info.message);
      if (info.message) setNotice(info.message);
      attempt += 1;
      setStatus("reconnecting");
      retryTimer = setTimeout(connect, backoffDelay(attempt));
    };

    const handleMessage = (event: MessageEvent) => {
      const frame = parseFrame(event.data);
      if (!frame) return;
      if (frame.type === "message") {
        setMessages((current) => mergeMessages(current, [frame.message]));
      } else if (frame.type === "system") {
        lineSeq.current += 1;
        const line: SystemLine = {
          key: `s${lineSeq.current}`,
          event: frame.event,
          username: frame.username,
          at: frame.at,
        };
        setSystem((current) => [...current, line].slice(-MAX_SYSTEM_LINES));
      } else if (frame.type === "presence") {
        setPresence({ members: frame.members, total: frame.total });
      } else if (frame.type === "error") {
        setNotice(translateServerError(frame.error));
      }
    };

    const connect = () => {
      const ws = new WebSocket(socketUrl(`/ws/${room}`));
      socket = ws;
      socketRef.current = ws;
      ws.onopen = () => {
        attempt = 0;
        refreshed = false;
        setStatus("open");
        setNotice(null);
        void loadHistory(); // catches up on anything missed while disconnected
      };
      ws.onmessage = handleMessage;
      ws.onclose = handleClose;
    };

    void loadHistory();
    connect();

    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      if (socket) {
        // Detach first: a late event from this socket must not touch the next room's state.
        socket.onopen = socket.onmessage = socket.onclose = null;
        socket.close();
      }
      socketRef.current = null;
    };
  }, [room, attemptToken]);

  const send = useCallback((content: string): boolean => {
    const socket = socketRef.current;
    if (socket?.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify({ content }));
    return true;
  }, []);

  const retry = useCallback(() => {
    setNotice(null);
    setAttemptToken((value) => value + 1);
  }, []);

  return { messages, system, presence, status, notice, stopped, send, retry };
}
