import { CHAT_API } from "@sn/api";

export const ROOM_PATTERN = /^[A-Za-z0-9_-]{1,32}$/;
export const MAX_MESSAGE_LENGTH = 2000;
export const POLL_INTERVAL_MS = 10_000;
export const BASE_DELAY_MS = 1000;
export const MAX_DELAY_MS = 15_000;
export const MAX_SYSTEM_LINES = 200;
export const ROOM_NAME_HINT = "Tên phòng chỉ gồm chữ, số, - và _ (tối đa 32 ký tự).";

export const CLOSE_MESSAGE_TOO_BIG = 1009;
export const CLOSE_POLICY = 1008;
export const CLOSE_TRY_LATER = 1013;

export interface ChatMessage {
  id: number;
  room: string;
  username: string;
  content: string;
  created_at: string;
}
export interface SystemLine {
  key: string;
  event: "join" | "leave";
  username: string;
  at: string;
}
export interface Member {
  userId: number;
  username: string;
}
export interface Presence {
  members: Member[];
  total: number;
}
export interface RoomInfo {
  room: string;
  users: number;
  /** Sorted, capped by the server (shorter than `users` when capped). */
  members: string[];
}

export type ServerFrame =
  | { type: "message"; message: ChatMessage }
  | { type: "system"; event: "join" | "leave"; username: string; at: string }
  | { type: "presence"; members: Member[]; total: number }
  | { type: "error"; error: string }
  | { type: "rooms"; rooms: RoomInfo[] };

export type TimelineItem =
  | { kind: "message"; key: string; time: number; message: ChatMessage }
  | { kind: "system"; key: string; time: number; line: SystemLine };

export function isValidRoom(name: string): boolean {
  return ROOM_PATTERN.test(name);
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

function toMessage(data: Record<string, unknown>): ChatMessage | null {
  const { id, room, username, content, created_at } = data;
  if (
    typeof id !== "number" ||
    typeof room !== "string" ||
    typeof username !== "string" ||
    typeof content !== "string" ||
    typeof created_at !== "string"
  ) {
    return null;
  }
  return { id, room, username, content, created_at };
}

function toMembers(value: unknown): Member[] | null {
  if (!Array.isArray(value)) return null;
  const members: Member[] = [];
  for (const item of value) {
    if (!isRecord(item) || typeof item.userId !== "number" || typeof item.username !== "string") {
      return null;
    }
    members.push({ userId: item.userId, username: item.username });
  }
  return members;
}

function toRooms(value: unknown): RoomInfo[] | null {
  if (!Array.isArray(value)) return null;
  const rooms: RoomInfo[] = [];
  for (const item of value) {
    if (!isRecord(item) || typeof item.room !== "string" || typeof item.users !== "number") {
      return null;
    }
    const members = item.members ?? [];
    if (!Array.isArray(members) || !members.every((name) => typeof name === "string")) return null;
    rooms.push({ room: item.room, users: item.users, members });
  }
  return rooms;
}

/** Parse one server text frame; null for anything that is not a well-formed known frame. */
export function parseFrame(raw: unknown): ServerFrame | null {
  if (typeof raw !== "string") return null;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(data)) return null;
  switch (data.type) {
    case "message": {
      const message = toMessage(data);
      return message && { type: "message", message };
    }
    case "system":
      if (
        (data.event === "join" || data.event === "leave") &&
        typeof data.username === "string" &&
        typeof data.at === "string"
      ) {
        return { type: "system", event: data.event, username: data.username, at: data.at };
      }
      return null;
    case "presence": {
      const members = toMembers(data.members);
      if (!members || typeof data.total !== "number") return null;
      return { type: "presence", members, total: data.total };
    }
    case "error":
      return typeof data.error === "string" ? { type: "error", error: data.error } : null;
    case "rooms": {
      const rooms = toRooms(data.rooms);
      return rooms && { type: "rooms", rooms };
    }
    default:
      return null;
  }
}

/** Parse the REST history payload, dropping malformed rows. */
export function parseHistory(data: unknown): ChatMessage[] {
  if (!Array.isArray(data)) return [];
  return data.flatMap((item) => {
    const message = isRecord(item) ? toMessage(item) : null;
    return message ? [message] : [];
  });
}

/** ChatWork filter: room name contains the room text AND (no user text OR a member name contains it). */
export function filterRooms(
  rooms: readonly RoomInfo[],
  roomFilter: string,
  userFilter: string,
): RoomInfo[] {
  const roomText = roomFilter.trim().toLowerCase();
  const userText = userFilter.trim().toLowerCase();
  return rooms.filter(
    (info) =>
      info.room.toLowerCase().includes(roomText) &&
      (userText === "" || info.members.some((name) => name.toLowerCase().includes(userText))),
  );
}

export function parseRooms(data: unknown): RoomInfo[] {
  return toRooms(data) ?? [];
}

/** Merge message lists, dropping duplicates by id and keeping id order. */
export function mergeMessages(...lists: readonly (readonly ChatMessage[])[]): ChatMessage[] {
  const byId = new Map<number, ChatMessage>();
  for (const list of lists) for (const message of list) byId.set(message.id, message);
  return [...byId.values()].sort((a, b) => a.id - b.id);
}

const timeOf = (iso: string): number => Date.parse(iso) || 0;

/** Messages and system lines in one chronological list (stable on ties). */
export function buildTimeline(
  messages: readonly ChatMessage[],
  system: readonly SystemLine[],
): TimelineItem[] {
  const items: TimelineItem[] = [
    ...messages.map(
      (message): TimelineItem => ({
        kind: "message",
        key: `m${message.id}`,
        time: timeOf(message.created_at),
        message,
      }),
    ),
    ...system.map(
      (line): TimelineItem => ({ kind: "system", key: line.key, time: timeOf(line.at), line }),
    ),
  ];
  return items.sort((a, b) => a.time - b.time);
}

export function systemText(line: Pick<SystemLine, "event" | "username">): string {
  return line.event === "join" ? `${line.username} đã vào phòng` : `${line.username} đã rời phòng`;
}

export type CloseAction = "retry" | "stop" | "session";
export interface CloseInfo {
  action: CloseAction;
  message: string | null;
}

const REFUSALS: Record<string, string> = {
  "Room is full": "Phòng đã đầy",
  "Too many active rooms": "Quá nhiều phòng đang hoạt động",
  "Too many connections": "Bạn mở quá nhiều kết nối",
  "Too many lobby connections": "Bạn mở quá nhiều kết nối",
};
const SERVER_ERRORS: Record<string, string> = {
  "Message must be 1-2000 characters": "Tin nhắn phải dài từ 1 đến 2000 ký tự.",
  "Only text frames are supported": "Chỉ hỗ trợ tin nhắn dạng văn bản.",
};

export function translateServerError(error: string): string {
  return SERVER_ERRORS[error] ?? error;
}

/** What to do after a socket closed with this code and reason. */
export function describeClose(code: number, reason: string): CloseInfo {
  if (code === CLOSE_POLICY) {
    return {
      action: "session",
      message: "Phiên đăng nhập hết hạn hoặc không hợp lệ, hoặc bạn gửi quá nhanh.",
    };
  }
  if (code === CLOSE_TRY_LATER) {
    return { action: "stop", message: REFUSALS[reason] ?? "Máy chủ đang bận. Hãy thử lại sau." };
  }
  if (code === CLOSE_MESSAGE_TOO_BIG) {
    return { action: "retry", message: "Tin nhắn quá lớn, kết nối bị ngắt." };
  }
  return { action: "retry", message: null };
}

export function backoffDelay(attempt: number): number {
  return Math.min(BASE_DELAY_MS * 2 ** Math.max(0, attempt - 1), MAX_DELAY_MS);
}

export function socketUrl(path: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${CHAT_API}${path}`;
}
