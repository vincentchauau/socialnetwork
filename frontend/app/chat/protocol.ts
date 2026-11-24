import { CHAT_API } from "@sn/api";
import { tr } from "./i18n";

export const MAX_MESSAGE_LENGTH = 2000;
const BASE_DELAY_MS = 1000;
const MAX_DELAY_MS = 15_000;
export const MAX_SYSTEM_LINES = 200;
export const HISTORY_PAGE = 50;

const CLOSE_MESSAGE_TOO_BIG = 1009;
export const CLOSE_POLICY = 1008;
export const CLOSE_TRY_LATER = 1013;

// ---- what the server sends and keeps ----

export type Visibility = "public" | "private";
export type JoinPolicy = "open" | "approval" | "invite";
export type Role = "owner" | "member";
export type MemberStatus = "pending" | "joined" | "left" | "kicked" | "banned";
export type RoomState = "open" | "closed" | "deleted";

export interface MyMembership {
  role: Role;
  status: MemberStatus;
  /** A joined member who reads and does not write. */
  muted: boolean;
  unread: number;
  /** False: the room is quiet, no badge of unread messages. */
  notify?: boolean;
  /** The newest message I had read up to. */
  last_read?: number;
}

export interface Room {
  id: number;
  slug: string;
  kind: "chat" | "dm";
  title: string;
  category: string;
  /** The address of its picture ("" for none). */
  avatar: string;
  /** The owner. */
  user_id: number;
  /** The name of the owner, for the tables (may be missing in older answers). */
  owner_name?: string;
  visibility: Visibility;
  join_policy: JoinPolicy;
  capacity: number;
  state: RoomState;
  members: number;
  online: number;
  me: MyMembership | null;
  /** Set when the list was searched: why this room is in it. */
  hit?: SearchHit | null;
  /** In the lists of my rooms: what was said last. */
  last_message?: LastMessage | null;
}

/** The newest message of a room, as a line. */
export interface LastMessage {
  username: string;
  kind: string;
  content: string;
  at: string;
}

/** Where the words of a search were found in a room. */
export interface SearchHit {
  fields: string[];
  members: string[];
  message: { id: number; username: string; content: string } | null;
}

export interface MemberRow {
  user_id: number;
  username: string;
  role: Role;
  status: MemberStatus;
  muted: boolean;
  /** The name and the picture of the person, as their profile lets the viewer see them. */
  name?: string;
  avatar?: string;
  status_reason?: string | null;
  online: boolean;
  /** Made by the platform: always there, they answer when somebody writes. */
  virtual?: boolean;
}

export interface ChatMessage {
  id: number;
  user_id: number;
  username: string;
  kind: string;
  content: string;
  reply_to_id: number | null;
  pinned_at: string | null;
  edited_at: string | null;
  created_at: string;
}
/** The number a line that is not kept (someone came online) is picked by: negative, so that it is never the id of a message. */
export const lineId = (key: string): number => -(Number(key.slice(1)) || 0) - 1;

export interface SystemLine {
  key: string;
  event: "join" | "leave";
  username: string;
  at: string;
}
export interface Person {
  user_id: number;
  username: string;
  online: boolean;
}
export interface Member {
  userId: number;
  username: string;
}
export interface Presence {
  members: Member[];
  total: number;
}
interface LiveRoom {
  room: string;
  users: number;
  /** Sorted, capped by the server (shorter than `users` when capped). */
  members: string[];
}

/** One sentence a virtual person reads aloud (PCM16 mono, base64; no sound when `pcm` is null), and a slide of words they share (no lines: taken away). */
export interface VoiceFrame {
  type: "voice";
  id: string;
  seq: number;
  last: boolean;
  userId: number;
  username: string;
  name: string;
  text: string;
  pcm: string | null;
  rate: number | null;
}
export interface SlideFrame {
  type: "slide";
  userId: number;
  name: string;
  title: string;
  lines: string[];
}

type ServerFrame =
  | VoiceFrame
  | SlideFrame
  | { type: "message"; message: ChatMessage }
  | { type: "system"; event: "join" | "leave"; username: string; at: string }
  | { type: "presence"; members: Member[]; total: number }
  | { type: "error"; error: string }
  | { type: "rooms"; rooms: LiveRoom[]; version: number; people: number; online: number }
  | { type: "deleted"; id: number }
  | { type: "pinned"; id: number; pinned: boolean }
  | { type: "edited"; id: number; content: string; edited_at: string }
  | { type: "member"; event: string; userId: number; username: string }
  | { type: "room" };

type TimelineItem =
  | { kind: "message"; key: string; time: number; message: ChatMessage }
  | { kind: "system"; key: string; time: number; line: SystemLine };

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;

function toMessage(data: Record<string, unknown>): ChatMessage | null {
  const { id, user_id, username, content, created_at } = data;
  if (
    typeof id !== "number" ||
    typeof username !== "string" ||
    typeof content !== "string" ||
    typeof created_at !== "string"
  ) {
    return null;
  }
  return {
    id,
    user_id: typeof user_id === "number" ? user_id : 0,
    username,
    kind: typeof data.kind === "string" ? data.kind : "text",
    content,
    reply_to_id: typeof data.reply_to_id === "number" ? data.reply_to_id : null,
    pinned_at: typeof data.pinned_at === "string" ? data.pinned_at : null,
    edited_at: typeof data.edited_at === "string" ? data.edited_at : null,
    created_at,
  };
}

function toMembers(value: unknown): Member[] | null {
  if (!Array.isArray(value)) return null;
  const members: Member[] = [];
  for (const item of value) {
    if (!isRecord(item) || typeof item.userId !== "number" || typeof item.username !== "string") return null;
    members.push({ userId: item.userId, username: item.username });
  }
  return members;
}

function toLiveRooms(value: unknown): LiveRoom[] | null {
  if (!Array.isArray(value)) return null;
  const rooms: LiveRoom[] = [];
  for (const item of value) {
    if (!isRecord(item) || typeof item.room !== "string" || typeof item.users !== "number") return null;
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
      if ((data.event === "join" || data.event === "leave") && typeof data.username === "string" && typeof data.at === "string") {
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
      const rooms = toLiveRooms(data.rooms);
      return (
        rooms && {
          type: "rooms",
          rooms,
          version: typeof data.version === "number" ? data.version : 0,
          people: typeof data.people === "number" ? data.people : 0,
          online: typeof data.online === "number" ? data.online : 0,
        }
      );
    }
    case "deleted":
      return typeof data.id === "number" ? { type: "deleted", id: data.id } : null;
    case "pinned":
      return typeof data.id === "number" && typeof data.pinned === "boolean" ? { type: "pinned", id: data.id, pinned: data.pinned } : null;
    case "edited":
      return typeof data.id === "number" && typeof data.content === "string" && typeof data.edited_at === "string"
        ? { type: "edited", id: data.id, content: data.content, edited_at: data.edited_at }
        : null;
    case "member":
      return typeof data.event === "string" && typeof data.user_id === "number" && typeof data.username === "string"
        ? { type: "member", event: data.event, userId: data.user_id, username: data.username }
        : null;
    case "room":
      return { type: "room" };
    case "voice":
      return typeof data.id === "string" && typeof data.seq === "number" && typeof data.user_id === "number" && typeof data.text === "string"
        ? {
            type: "voice", id: data.id, seq: data.seq, last: data.last === true, userId: data.user_id, username: String(data.username ?? ""),
            name: String(data.name ?? data.username ?? ""), text: data.text, pcm: typeof data.pcm === "string" ? data.pcm : null,
            rate: typeof data.rate === "number" ? data.rate : null,
          }
        : null;
    case "slide":
      return typeof data.user_id === "number" && Array.isArray(data.lines)
        ? { type: "slide", userId: data.user_id, name: String(data.name ?? ""), title: String(data.title ?? ""), lines: data.lines.filter((l): l is string => typeof l === "string") }
        : null;
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

/** Merge message lists, dropping duplicates by id and keeping id order. */
export function mergeMessages(...lists: readonly (readonly ChatMessage[])[]): ChatMessage[] {
  const byId = new Map<number, ChatMessage>();
  for (const list of lists) for (const message of list) byId.set(message.id, message);
  return [...byId.values()].sort((a, b) => a.id - b.id);
}

const timeOf = (iso: string): number => Date.parse(iso) || 0;

/** Messages and system lines in one chronological list (stable on ties). */
export function buildTimeline(messages: readonly ChatMessage[], system: readonly SystemLine[]): TimelineItem[] {
  const items: TimelineItem[] = [
    ...messages.map((message): TimelineItem => ({ kind: "message", key: `m${message.id}`, time: timeOf(message.created_at), message })),
    ...system.map((line): TimelineItem => ({ kind: "system", key: line.key, time: timeOf(line.at), line })),
  ];
  return items.sort((a, b) => a.time - b.time);
}

/**
 * The line of the conversation about a change (said by `system`): the content says what happened and to whom, `joined:bob`; for the people
 * a virtual person was added by, `virtual_added:<how many>:<who added them>`; when a game of the room is over, `game_over:<winner>:<days>`.
 */
export function changeText(content: string): string {
  const colon = content.indexOf(":");
  const what = colon < 0 ? content : content.slice(0, colon);
  const rest = colon < 0 ? "" : content.slice(colon + 1);
  if (what === "virtual_added") {
    const split = rest.indexOf(":");
    return tr("rm_sys_virtual_added", { p0: split < 0 ? "" : rest.slice(split + 1), p1: split < 0 ? rest : rest.slice(0, split) });
  }
  if (what === "game_over") {
    const split = rest.indexOf(":");
    const winner = split < 0 ? rest : rest.slice(0, split);
    const days = split < 0 ? "" : rest.slice(split + 1);
    return winner === "DRAW" ? tr("rm_sys_game_draw", { p1: days }) : tr("rm_sys_game_over", { p0: tr(`rm_sys_faction_${winner}`), p1: days });
  }
  if (what === "ai_usage") {
    const [tokensIn, tokensOut, ms, ...who] = rest.split(":");
    return tr("rm_sys_ai_usage", { p0: who.join(":"), p1: tokensIn, p2: tokensOut, p3: (Number(ms) / 1000).toFixed(1) });
  }
  if (what === "meeting") return tr("rm_sys_meeting");  // (no username: the mode after the colon is not shown)
  const username = rest;
  switch (what) {
    case "joined":
      return tr("rm_sys_joined", { p0: username });
    case "left":
      return tr("rm_sys_left", { p0: username });
    case "kicked":
      return tr("rm_sys_kicked", { p0: username });
    case "banned":
      return tr("rm_sys_banned", { p0: username });
    case "closed":
      return tr("rm_sys_closed", { p0: username });
    case "reopened":
      return tr("rm_sys_reopened", { p0: username });
    case "transferred":
      return tr("rm_sys_transferred", { p0: username });
    case "call":
      return tr("rm_sys_call", { p0: username });
    case "screen":
      return tr("rm_sys_screen", { p0: username });
    case "game":
      return tr("rm_sys_game", { p0: username });
    default:
      return content;
  }
}

export function systemText(line: Pick<SystemLine, "event" | "username">): string {
  return line.event === "join" ? tr("p0_da_vao_phong", { p0: line.username }) : tr("p0_da_roi_phong", { p0: line.username });
}

// ---- rooms the way the list and the header show them ----

export const isOwner = (me: MyMembership | null | undefined): boolean => me?.status === "joined" && me.role === "owner";


export function stateText(state: RoomState): string | null {
  switch (state) {
    case "closed":
      return tr("rm_phong_da_dong");
    case "deleted":
      return tr("rm_phong_da_xoa");
    default:
      return null;
  }
}

/** A room has two statuses: Public (anyone may come in) or Private (its owner lets people in). A chat of two is always Private. */
export const isPrivateRoom = (room: Pick<Room, "kind" | "join_policy">): boolean => room.kind === "dm" || room.join_policy !== "open";

/** How full a room is: `12/200 chỗ`. */
export function slotsText(room: Pick<Room, "members" | "capacity">): string {
  return tr("rm_p0_p1_cho", { p0: room.members, p1: room.capacity });
}

/** A link that takes someone to a room, from wherever it is opened. */
export function roomLink(slug: string): string {
  return `${window.location.origin}/chat#room=${encodeURIComponent(slug)}`;
}

/** `#room=<slug>` of the address bar. */
export function readHash(hash: string): { room: string | null } {
  return { room: new URLSearchParams(hash.replace(/^#/, "")).get("room") };
}

// ---- closing a socket ----

type CloseAction = "retry" | "stop" | "session" | "removed";
interface CloseInfo {
  action: CloseAction;
  message: string | null;
}

const REFUSALS: Record<string, string> = {
  get "Room is full"() { return tr("phong_da_day"); },
  get "Too many active rooms"() { return tr("qua_nhieu_phong_dang_hoat_dong"); },
  get "Too many connections"() { return tr("ban_mo_qua_nhieu_ket_noi"); },
  get "Too many lobby connections"() { return tr("ban_mo_qua_nhieu_ket_noi"); },
};

/** Why a socket was shut by a rule of the room (not an expired session), by the reason the server gave. */
const ROOM_REASONS: Record<string, string> = {
  get "Room not found"() { return tr("rm_khong_tim_thay_phong"); },
  get "You are not a member of this room"() { return tr("rm_ban_chua_la_thanh_vien"); },
  get "Waiting for approval"() { return tr("rm_dang_cho_duyet"); },
  get "You are banned from this room"() { return tr("rm_ban_bi_chan"); },
  get "You left the room"() { return tr("rm_ban_da_roi_phong"); },
  get "You were removed from the room"() { return tr("rm_ban_bi_moi_ra"); },
  get "Room deleted"() { return tr("rm_phong_da_bi_xoa"); },
};

const SERVER_ERRORS: Record<string, string> = {
  get "Message must be 1-2000 characters"() { return tr("tin_nhan_phai_dai_tu_1"); },
  get "Only text frames are supported"() { return tr("chi_ho_tro_tin_nhan_dang"); },
  get "Room is not open"() { return tr("rm_phong_dang_khong_mo"); },
  get "You are muted"() { return tr("rm_ban_dang_bi_tat_tieng"); },
  get "Only moderators can post here"() { return tr("rm_chi_quan_tri_moi_duoc_dang"); },
  get "You are not a member of this room"() { return tr("rm_ban_chua_la_thanh_vien"); },
  get "Waiting for approval"() { return tr("rm_dang_cho_duyet"); },
  get "You are banned from this room"() { return tr("rm_ban_bi_chan"); },
};

export function translateServerError(error: string): string {
  return SERVER_ERRORS[error] ?? error;
}

/** What to do after a socket closed with this code and reason. */
export function describeClose(code: number, reason: string): CloseInfo {
  if (code === CLOSE_POLICY) {
    if (reason in ROOM_REASONS) return { action: "removed", message: ROOM_REASONS[reason] };
    return { action: "session", message: tr("phien_dang_nhap_het_han_hoac") };
  }
  if (code === CLOSE_TRY_LATER) {
    return { action: "stop", message: REFUSALS[reason] ?? tr("may_chu_dang_ban_hay_thu") };
  }
  if (code === CLOSE_MESSAGE_TOO_BIG) {
    return { action: "retry", message: tr("tin_nhan_qua_lon_ket_noi") };
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

/** What the server writes in place of a person whose account is gone. */
const DELETED_USERNAME = "Người dùng đã xóa";
