import { WEREWOLF_API } from "./api";
import type { ChatMessage, RoomState, ServerFrame } from "./types";
import { trServerDeep } from "@sn/lib/i18n";

export const MAX_RETRY_DELAY_MS = 15_000;
const BASE_RETRY_DELAY_MS = 1_000;
const CHAT_KEEP = 400;

export const CLOSE_POLICY = 1008;
export const CLOSE_GONE = 1001;

export function socketUrl(code: string, location: Pick<Location, "protocol" | "host"> = window.location): string {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${location.host}${WEREWOLF_API}/ws/${encodeURIComponent(code)}`;
}

/** Exponential backoff with a cap: 1s, 2s, 4s ... 15s. */
export function retryDelay(attempt: number): number {
  return Math.min(MAX_RETRY_DELAY_MS, BASE_RETRY_DELAY_MS * 2 ** Math.max(0, attempt));
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** Parses a text frame; anything that is not a known, well-formed server frame gives null. */
export function parseFrame(raw: unknown): ServerFrame | null {
  if (typeof raw !== "string") return null;
  let data: unknown;
  try {
    data = trServerDeep(JSON.parse(raw));
  } catch {
    return null;
  }
  if (!isObject(data)) return null;
  if (data.type === "state" && isObject(data.state) && Array.isArray(data.state.members)) {
    return { type: "state", state: sanitizeRoom(data.state as unknown as RoomState) };
  }
  if (data.type === "chat" && isObject(data.message) && typeof data.message.seq === "number") {
    return { type: "chat", message: data.message as unknown as ChatMessage };
  }
  if (data.type === "error" && typeof data.error === "string") return { type: "error", error: data.error };
  return null;
}

/**
 * Defence in depth for the privacy rules (API.md): in the lobby only your own seat may show a role,
 * whatever the server sent. In a running game the server already limits every field to what you know.
 */
export function sanitizeRoom(state: RoomState): RoomState {
  if (state.game) return state;  // (the host keeps `setup`: it is theirs to see)
  return {
    ...state,
    members: state.members.map((member) =>
      member.isYou ? member : { ...member, faction: null, ability: null },
    ),
  };
}
