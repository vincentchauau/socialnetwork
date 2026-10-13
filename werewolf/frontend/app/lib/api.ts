import { apiFetch } from "@sn/api";

import type {
  ChatMessage,
  CreateBody,
  Game,
  HistoryEntry,
  RoomEnvelope,
  RoomSummary,
  SetupMeta,
  SetupSeat,
} from "./types";

export const WEREWOLF_API = "/api/werewolf";

const post = <T>(path: string, body?: unknown) =>
  apiFetch<T>(`${WEREWOLF_API}${path}`, {
    method: "POST",
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });

const roomPath = (code: string) => `/rooms/${encodeURIComponent(code)}`;

export const werewolfApi = {
  meta: () => apiFetch<SetupMeta>(`${WEREWOLF_API}/setup/meta`),
  random: (count: number) => apiFetch<{ seats: SetupSeat[] }>(`${WEREWOLF_API}/setup/random?count=${count}`),
  rooms: () => apiFetch<RoomSummary[]>(`${WEREWOLF_API}/rooms`),
  room: (code: string) => apiFetch<RoomEnvelope>(`${WEREWOLF_API}${roomPath(code)}`),
  create: (body: CreateBody) => post<RoomEnvelope>("/rooms", body),
  join: (code: string) => post<RoomEnvelope>(`${roomPath(code)}/join`),
  leave: (code: string) => post<{ left: boolean }>(`${roomPath(code)}/leave`),
  start: (code: string) => post<RoomEnvelope>(`${roomPath(code)}/start`),
  addBots: (code: string, count: number) => post<RoomEnvelope>(`${roomPath(code)}/bots`, { count }),
  act: (code: string, target: number, kind: "ability" | "wolf") =>
    post<RoomEnvelope>(`${roomPath(code)}/action`, { target, kind }),
  chat: (code: string, text: string, target: number) =>
    post<{ id: string; message: ChatMessage }>(`${roomPath(code)}/chat`, { text, target }),
  force: (code: string) => post<RoomEnvelope>(`${roomPath(code)}/force`),
  rematch: (code: string) => post<RoomEnvelope>(`${roomPath(code)}/rematch`),
  reset: (code: string) => post<RoomEnvelope>(`${roomPath(code)}/reset`),
  perspective: (code: string, seat: number) =>
    apiFetch<Game>(`${WEREWOLF_API}${roomPath(code)}/perspective/${seat}`),
  history: (limit = 50) => apiFetch<HistoryEntry[]>(`${WEREWOLF_API}/me/history?limit=${limit}`),
};
