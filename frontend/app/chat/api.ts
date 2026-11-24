import { CHAT_API, apiFetch } from "@sn/api";

import type { ChatMessage, MemberRow, Room } from "./protocol";
import { HISTORY_PAGE, parseHistory } from "./protocol";

const SEARCH_LIMIT = 30; // the hits of a search, newest last

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});
const path = (slug: string, rest = "") => `${CHAT_API}/rooms/${encodeURIComponent(slug)}${rest}`;

/** What someone fills in to make a room (the server checks every limit again). */
export interface NewRoom {
  title: string;
  category: string;
  avatar: string;
  visibility: "public" | "private";
  join_policy: "open" | "approval" | "invite";
  capacity: number;
  slug?: string;
}

export type RoomChanges = Partial<Omit<NewRoom, "slug">> & { state?: "open" | "closed" };

interface MemberChanges {
  status?: "joined" | "banned";
  reason?: string;
  muted?: boolean;
}

export interface RoomQuery {
  scope: "public" | "mine" | "past" | "requests";
  q?: string;
  category?: string;
  region?: string;
}

/** What the browser needs to join the call of a room: where LiveKit is, the name of its room and the ticket of this person. */
export interface Meeting {
  id: number;
  room: string;
  name: string;
  server: string;
  token: string;
}

const meetingPath = (slug: string, rest = "") => `${CHAT_API}/rooms/${encodeURIComponent(slug)}/meeting${rest}`;

/** The room's one meeting: its call (a LiveKit room): the ticket to join it. */
export const meetingApi = {
  /** The open meeting of the room, or a 404 error when there is none. */
  current: (slug: string) => apiFetch<Meeting>(meetingPath(slug)),
  /** Start the meeting (the server reuses an open one) and say so in the conversation. */
  start: (slug: string) => apiFetch<Meeting>(meetingPath(slug, "/start"), json("POST")),
  end: (slug: string) => apiFetch<void>(meetingPath(slug, "/end"), json("POST")),
};

export const chatApi = {
  rooms: ({ scope, q = "", category = "", region = "" }: RoomQuery) => {
    const params = new URLSearchParams({ scope });
    if (q.trim()) params.set("q", q.trim());
    if (category.trim()) params.set("category", category.trim());
    if (region.trim()) params.set("region", region.trim());
    return apiFetch<Room[]>(`${CHAT_API}/rooms?${params}`);
  },
  room: (slug: string) => apiFetch<Room>(path(slug)),
  create: (body: NewRoom) => apiFetch<Room>(`${CHAT_API}/rooms`, json("POST", body)),
  update: (slug: string, changes: RoomChanges) => apiFetch<Room>(path(slug), json("PATCH", changes)),
  remove: (slug: string, permanent = false) => apiFetch<void>(path(slug, permanent ? "?permanent=true" : ""), json("DELETE")),
  join: (slug: string) => apiFetch<Room>(path(slug, "/join"), json("POST")),
  /** The code of the room's Werewolf game (made the first time) and how many seats it should have. */
  game: (slug: string, follow = false) => apiFetch<{ code: string; seats: number }>(path(slug, follow ? "/game?follow=1" : "/game"), json("POST")),
  /** What only I decide about my place in the room. */
  /** Say yes to a private chat that someone asked for. */
  acceptRequest: (slug: string) => apiFetch<Room>(path(slug, "/accept"), json("POST")),
  /** Say no (the asker is not told). */
  declineRequest: (slug: string) => apiFetch<void>(path(slug, "/decline"), json("POST")),
  /** What waits for me: unread messages, requests to write to me, notices. */
  summary: () => apiFetch<{ messages: number; requests: number; notices: number }>(`${CHAT_API}/inbox/summary`),
  hide: (slug: string) => apiFetch<void>(path(slug, "/hide"), json("POST")),
  leave: (slug: string) => apiFetch<void>(path(slug, "/leave"), json("POST")),
  transfer: (slug: string, userId: number) => apiFetch<Room>(path(slug, "/transfer"), json("POST", { user_id: userId })),
  read: (slug: string, messageId: number) => apiFetch<void>(path(slug, "/read"), json("POST", { message_id: messageId })),
  /** The people of the room; `q` keeps the ones whose name holds those letters, `status` the ones in that state. */
  /** Say something aloud to the virtual people of the room: the answer comes back with its voice (PCM16, base64). */
  voiceMessage: (slug: string, pcm: string, rate: number) =>
    apiFetch<{ text: string; answered: string }>(path(slug, "/voice-message"), json("POST", { pcm, rate })),
  members: (slug: string, q = "", status = "") => {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (status) params.set("status", status);
    return apiFetch<MemberRow[]>(path(slug, `/members${params.size ? `?${params}` : ""}`));
  },
  member: (slug: string, userId: number) => apiFetch<MemberRow>(path(slug, `/members/${userId}`)),
  /** The owner brings a person in by name or id (or back, after they left or were sent away). */
  addMember: (slug: string, who: { username: string } | { user_id: number }) => apiFetch<MemberRow>(path(slug, "/members"), json("POST", who)),
  changeMember: (slug: string, userId: number, changes: MemberChanges) =>
    apiFetch<MemberRow>(path(slug, `/members/${userId}`), json("PATCH", changes)),
  removeMember: (slug: string, userId: number) => apiFetch<void>(path(slug, `/members/${userId}`), json("DELETE")),
  history: async (slug: string, before?: number): Promise<ChatMessage[]> => {
    const params = new URLSearchParams({ limit: String(HISTORY_PAGE) });
    if (before !== undefined) params.set("before", String(before));
    return parseHistory(await apiFetch<unknown>(path(slug, `/messages?${params}`)));
  },
  /** The messages that hold those words, any accent and any case (the newest of them last). */
  searchMessages: async (slug: string, q: string): Promise<ChatMessage[]> => {
    const params = new URLSearchParams({ limit: String(SEARCH_LIMIT), q: q.trim() });
    return parseHistory(await apiFetch<unknown>(path(slug, `/messages?${params}`)));
  },
  /** Send without the socket (the same rules); the message arrives to everybody through the socket. */
  /** The author changes the words of a text message; the change arrives to everybody through the socket. */
  editMessage: (slug: string, id: number, content: string) => apiFetch<ChatMessage>(path(slug, `/messages/${id}`), json("PATCH", { content })),
  /** A form of a card, sent by the person it is for; the card changes (and the result follows) through the socket. */
  submitCard: (slug: string, id: number, values: Record<string, unknown>) => apiFetch<ChatMessage>(path(slug, `/cards/${id}/submit`), json("POST", { values })),
  /** A button of a card (`item` is the row of a list it is on). */
  actCard: (slug: string, id: number, action: number, item?: number) => apiFetch<ChatMessage>(path(slug, `/cards/${id}/act`), json("POST", item === undefined ? { action } : { item, action })),
  /** Bring `count` virtual people into the room at once (the ones I drew first, then new ones); they answer what is written there. */
  addVirtual: (slug: string, count: number) => apiFetch<{ added: { user_id: number; username: string; display_name: string }[]; wanted: number; why: string | null }>(path(slug, "/virtual"), json("POST", { count })),
  /** The person a card asks says yes or no; the changed card comes back through the socket. */
  answerCard: (slug: string, id: number, action: "confirm" | "cancel") => apiFetch<ChatMessage>(path(slug, `/cards/${id}/${action}`), json("POST")),
  deleteMessage: (slug: string, id: number) => apiFetch<void>(path(slug, `/messages/${id}`), json("DELETE")),
  pin: (slug: string, id: number) => apiFetch<void>(path(slug, `/messages/${id}/pin`), json("PUT")),
  unpin: (slug: string, id: number) => apiFetch<void>(path(slug, `/messages/${id}/pin`), json("DELETE")),
  openDm: (userId: number) => apiFetch<Room>(`${CHAT_API}/dm`, json("POST", { user_id: userId })),
};

// ---- the people side (friends, blocks, reports, notices, companions), over the same `/api/chat` ----

export type Relation = "none" | "friends" | "requested" | "incoming";

export interface Person {
  user_id: number;
  username: string;
  display_name: string;
  headline: string;
  region: string;
  avatar: string;
  /** Null when the viewer may not read it (a stranger, and its owner kept it for friends). */
  summary: string | null;
  relation: Relation;
  /** I blocked this person. */
  blocked: boolean;
  /** Whether they have the chat open: asked of the chat (`onlineOf`), not of the social side. */
  online?: boolean;
  /** Made by the platform, not a person. */
  virtual: boolean;
  /** Of a virtual person only. */
  age: number | null;
  interests: string[];
  /** I drew this virtual person. */
  companion: boolean;
}

export const REPORT_REASONS = ["spam", "abuse", "impersonation", "illegal", "other"] as const;
export type ReportReason = (typeof REPORT_REASONS)[number];

interface NewReport {
  target_type: "user" | "message" | "room" | "object";
  target_id: string;
  reason: ReportReason;
  details: string;
}

const url = (rest: string) => `${CHAT_API}${rest}`;

export const socialApi = {
  person: (username: string) => apiFetch<Person>(url(`/people/${encodeURIComponent(username)}`)),
  ask: (userId: number) => apiFetch<Person>(url(`/friends/${userId}`), json("POST")),
  accept: (userId: number) => apiFetch<Person>(url(`/friends/${userId}/accept`), json("POST")),
  decline: (userId: number) => apiFetch<void>(url(`/friends/${userId}/decline`), json("POST")),
  unfriend: (userId: number) => apiFetch<void>(url(`/friends/${userId}`), json("DELETE")),
  block: (userId: number) => apiFetch<void>(url(`/blocks/${userId}`), json("POST")),
  unblock: (userId: number) => apiFetch<void>(url(`/blocks/${userId}`), json("DELETE")),
  report: (body: NewReport) => apiFetch<{ id: number }>(url("/reports"), json("POST", body)),
  /** The reports I made that nobody has looked at yet (each can be taken back). */
  myReports: () => apiFetch<{ id: number; target_type: string; target_id: string }[]>(url("/reports/mine")),
  unreport: (reportId: number) => apiFetch<void>(url(`/reports/${reportId}`), json("DELETE")),
};
