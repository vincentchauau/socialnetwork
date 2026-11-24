"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { type RoomQuery, chatApi } from "./api";
import type { Room } from "./protocol";
import type { LobbyMode } from "./useLobby";
import { errorMessage } from "./errors";

const POLL_INTERVAL_MS = 10_000;

interface Rooms {
  rooms: Room[];
  loading: boolean;
  error: string | null;
  /** Fetch the list again now (after something changed it). */
  reload: () => Promise<void>;
}

/** The list of rooms of a scope, fetched again when the lobby says rooms changed and polled while it is not live. */
export function useRooms(query: RoomQuery, lobby: { version: number; mode: LobbyMode }): Rooms {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const { scope, q = "", category = "", region = "" } = query;

  const reload = useCallback(async () => {
    const ticket = ++latest.current; // an answer to an older question must not overwrite a newer one
    try {
      const list = await chatApi.rooms({ scope, q, category, region });
      if (ticket !== latest.current) return;
      setRooms(list);
      setError(null);
    } catch (caught) {
      if (ticket === latest.current) setError(errorMessage(caught));
    } finally {
      if (ticket === latest.current) setLoading(false);
    }
  }, [scope, q, category, region]);

  useEffect(() => {
    setLoading(true);
    void reload();
  }, [reload, lobby.version]);

  useEffect(() => {
    if (lobby.mode !== "polling") return;
    const timer = setInterval(() => void reload(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [lobby.mode, reload]);

  return { rooms, loading, error, reload };
}
