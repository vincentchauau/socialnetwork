"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { refreshSession } from "@sn/api";
import { chatApi } from "./api";
import { CALL_FRAME_EVENT } from "./meetingRequest";
import {
  ChatMessage,
  HISTORY_PAGE,
  MAX_SYSTEM_LINES,
  Presence,
  SystemLine,
  backoffDelay,
  describeClose,
  lineId,
  mergeMessages,
  parseFrame,
  socketUrl,
  translateServerError,
} from "./protocol";
import { tr } from "./i18n";

export type ConnStatus = "connecting" | "open" | "reconnecting" | "closed";
/** Why the socket stays shut: the session ended, the server refused, or the room closed its door to this person. */
type StopReason = "session" | "refused" | "removed" | null;

interface RoomChat {
  messages: ChatMessage[];
  system: SystemLine[];
  presence: Presence | null;
  status: ConnStatus;
  notice: string | null;
  stopped: StopReason;
  /** True while older messages remain to be fetched. */
  hasOlder: boolean;
  /** Changes whenever the members or the room itself changed, so the panels can fetch them again. */
  roomVersion: number;
  send: (content: string, replyTo?: number | null) => boolean;
  retry: () => void;
  loadOlder: () => Promise<void>;
  /** Take lines that are not kept (someone came online) off the screen, by `lineId`. */
  dismissLines: (ids: readonly number[]) => void;
}

/** History (REST) + live frames (/ws/{room}) of one room, with reconnect and cleanup. */
export function useRoomChat(room: string): RoomChat {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [system, setSystem] = useState<SystemLine[]>([]);
  const [presence, setPresence] = useState<Presence | null>(null);
  const [status, setStatus] = useState<ConnStatus>("connecting");
  const [notice, setNotice] = useState<string | null>(null);
  const [stopped, setStopped] = useState<StopReason>(null);
  const [hasOlder, setHasOlder] = useState(false);
  const [roomVersion, setRoomVersion] = useState(0);
  const [attemptToken, setAttemptToken] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  const lineSeq = useRef(0);
  messagesRef.current = messages;

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let refreshed = false; // one session refresh per failed connection, never a loop

    setStopped(null);
    setStatus("connecting");

    // Merged by id, so history and live messages can arrive in any order.
    const loadHistory = (first: boolean) =>
      chatApi
        .history(room)
        .then((list) => {
          if (cancelled) return;
          setMessages((current) => mergeMessages(list, current));
          if (first) setHasOlder(list.length >= HISTORY_PAGE);
        })
        .catch(() => {
          if (!cancelled) setNotice(tr("khong_tai_duoc_lich_su_tin"));
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
      if (info.action === "removed") return stop("removed", info.message);
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
        const line: SystemLine = { key: `s${lineSeq.current}`, event: frame.event, username: frame.username, at: frame.at };
        setSystem((current) => [...current, line].slice(-MAX_SYSTEM_LINES));
      } else if (frame.type === "presence") {
        setPresence({ members: frame.members, total: frame.total });
      } else if (frame.type === "error") {
        setNotice(translateServerError(frame.error));
      } else if (frame.type === "deleted") {
        setMessages((current) => current.filter((message) => message.id !== frame.id));
      } else if (frame.type === "edited") {
        setMessages((current) => current.map((message) => (message.id === frame.id ? { ...message, content: frame.content, edited_at: frame.edited_at } : message)));
      } else if (frame.type === "pinned") {
        const at = new Date().toISOString();
        setMessages((current) => current.map((message) => (message.id === frame.id ? { ...message, pinned_at: frame.pinned ? at : null } : message)));
      } else if (frame.type === "member" || frame.type === "room") {
        setRoomVersion((value) => value + 1);
      } else if (frame.type === "voice" || frame.type === "slide") {
        window.dispatchEvent(new CustomEvent(CALL_FRAME_EVENT, { detail: frame })); // (the call of the room, if it is on screen, plays and shows it)
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
        void loadHistory(false); // catches up on anything missed while disconnected
      };
      ws.onmessage = handleMessage;
      ws.onclose = handleClose;
    };

    void loadHistory(true);
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

  const send = useCallback((content: string, replyTo?: number | null): boolean => {
    const socket = socketRef.current;
    if (socket?.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(replyTo ? { content, reply_to: replyTo } : { content }));
    return true;
  }, []);

  const retry = useCallback(() => {
    setNotice(null);
    setAttemptToken((value) => value + 1);
  }, []);

  const loadOlder = useCallback(async () => {
    const oldest = messagesRef.current[0]?.id;
    if (oldest === undefined) return;
    try {
      const older = await chatApi.history(room, oldest);
      setMessages((current) => mergeMessages(older, current));
      setHasOlder(older.length >= HISTORY_PAGE);
    } catch {
      setNotice(tr("khong_tai_duoc_lich_su_tin"));
    }
  }, [room]);

  /** Take lines that are not kept (someone came online) off the screen: they were never saved, so this is all deleting them means. */
  const dismissLines = useCallback((ids: readonly number[]) => setSystem((current) => current.filter((line) => !ids.includes(lineId(line.key)))), []);
  return { messages, system, presence, status, notice, stopped, hasOlder, roomVersion, send, retry, loadOlder, dismissLines };
}
