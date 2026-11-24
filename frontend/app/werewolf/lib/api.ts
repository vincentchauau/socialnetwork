import { apiFetch } from "@sn/api";

import type {
  ChatMessage,
  Game,
  HistoryEntry,
  LeaderEntry,
  RoomEnvelope,
  SetupSeat,
  SetupMeta,
} from "./types";

/** The game is an app of its own: its routes (and its sockets) are under /api/werewolf. */
export const WEREWOLF_API = "/api/werewolf";

const post = <T>(path: string, body?: unknown) =>
  apiFetch<T>(`${WEREWOLF_API}${path}`, {
    method: "POST",
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });

const roomPath = (code: string) => `/rooms/${encodeURIComponent(code)}`;

export const werewolfApi = {
  meta: () => apiFetch<SetupMeta>(`${WEREWOLF_API}/setup/meta`),
  room: (code: string) => apiFetch<RoomEnvelope>(`${WEREWOLF_API}${roomPath(code)}`),
  join: (code: string) => post<RoomEnvelope>(`${roomPath(code)}/join`),
  leave: (code: string) => post<{ left: boolean }>(`${roomPath(code)}/leave`),
  start: (code: string) => post<RoomEnvelope>(`${roomPath(code)}/start`),
  /** The host sets the role of every seat: `{ random: true }` deals them, `{ seats }` sets them one by one, `{}` leaves it to the start. */
  roles: (code: string, body: { random?: boolean; seats?: SetupSeat[]; banned?: string[] }) => post<RoomEnvelope>(`${roomPath(code)}/roles`, body),
  act: (code: string, target: number, kind: "ability" | "wolf") =>
    post<RoomEnvelope>(`${roomPath(code)}/action`, { target, kind }),
  force: (code: string) => post<RoomEnvelope>(`${roomPath(code)}/force`),
  rematch: (code: string) => post<RoomEnvelope>(`${roomPath(code)}/rematch`),
  reset: (code: string) => post<RoomEnvelope>(`${roomPath(code)}/reset`),
  perspective: (code: string, seat: number) =>
    apiFetch<Game>(`${WEREWOLF_API}${roomPath(code)}/perspective/${seat}`),
  leaderboard: (season: "month" | "all" = "all") => apiFetch<LeaderEntry[]>(`${WEREWOLF_API}/leaderboard?season=${season}`),
  history: (limit = 50) => apiFetch<HistoryEntry[]>(`${WEREWOLF_API}/me/history?limit=${limit}`),
};
