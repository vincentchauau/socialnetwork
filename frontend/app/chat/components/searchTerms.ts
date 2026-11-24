import { type Room, isPrivateRoom } from "../protocol";

/** What the box "Words or column:value" understands in the tables of the chat (the same box as the Table pane). */
export const ROOM_FIELDS = ["kind", "status", "state", "owner", "title", "category"] as const;
export const MEMBER_FIELDS = ["status", "role", "name"] as const;
export const MESSAGE_FIELDS = ["from"] as const;

export type Named = Record<string, string>;

/** The terms of the box split in the words (to look for, at the server) and the `field:value` ones this table knows (to filter the rows here). */
export function splitTerms(terms: readonly string[], fields: readonly string[]): { words: string; named: Named } {
  const named: Named = {};
  const words: string[] = [];
  for (const term of terms) {
    const at = term.indexOf(":");
    const field = at > 0 ? term.slice(0, at).trim().toLowerCase() : "";
    if (field && fields.includes(field)) named[field] = term.slice(at + 1).trim().toLowerCase();
    else words.push(term);
  }
  return { words: words.join(" "), named };
}

export const has = (text: string | null | undefined, wanted: string): boolean => (text ?? "").toLowerCase().includes(wanted);

/** Does the room hold what the `field:value` terms ask (`kind:dm`, `status:private`, `state:closed`, `owner:alice`, `title:…`, `category:…`)? */
export function roomMatches(room: Room, named: Named): boolean {
  if (named.kind && room.kind !== named.kind) return false;
  if (named.status && (isPrivateRoom(room) ? "private" : "public") !== named.status) return false;
  if (named.state && room.state !== named.state) return false;
  return has(room.owner_name, named.owner ?? "") && has(room.title, named.title ?? "") && has(room.category, named.category ?? "");
}
