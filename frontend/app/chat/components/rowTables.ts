import type { ColumnInfo, Row, TableInfo } from "@sn/compounds/crudModel";

import type { RoomChanges } from "../api";
import { type ChatMessage, type MemberRow, type Room, isPrivateRoom } from "../protocol";
import { tr } from "../i18n";

/**
 * What a row of the rooms, the members and the messages is in the form of the Table pane ("Edit row"): the same form, over these three. Each
 * has the columns a person may change, and the ones that are only shown (they go under "System info"). The rules stay the server's: a form
 * of these only turns what was typed into the calls the chat already has (`changesOfRoom`, `changesOfMember`).
 */
const column = (name: string, type: ColumnInfo["type"] = "string", extra: Partial<ColumnInfo> = {}): ColumnInfo => ({ name, type, nullable: false, readonly: false, secret: false, ...extra });

export const ROOM_TABLE: TableInfo = {
  name: "rooms",
  label: "rooms",
  pk: ["slug"],
  writable: true,
  columns: [
    column("slug", "string", { readonly: true }),
    column("title"),
    column("category"),
    column("avatar"), // the address of its picture
    column("status"), // public | private
    column("capacity", "int"),
    column("state"), // open | closed
    column("owner_name", "string", { readonly: true }),
  ],
};

export const MEMBER_TABLE: TableInfo = {
  name: "room_members",
  label: "room_members",
  pk: ["username"],
  writable: true,
  columns: [
    column("username", "string", { readonly: true }),
    column("role"), // member | owner (owner hands the room over)
    column("status"), // joined | banned
    column("muted", "bool"), // may read, may not write
    column("status_reason", "string", { nullable: true }), // why: kept with a ban
  ],
};

export const MESSAGE_TABLE: TableInfo = {
  name: "messages",
  label: "messages",
  pk: ["id"],
  writable: true,
  columns: [column("id", "int", { readonly: true }), column("username", "string", { readonly: true }), column("content", "text"), column("created_at", "datetime", { readonly: true })],
};

export const roomRow = (room: Room): Row => ({
  slug: room.slug,
  title: room.title,
  category: room.category,
  avatar: room.avatar ?? "",
  status: isPrivateRoom(room) ? "private" : "public",
  capacity: room.capacity,
  state: room.state,
  owner_name: room.owner_name ?? "",
});

export const memberRow = (member: MemberRow): Row => ({
  username: member.username,
  role: member.role,
  status: member.status,
  muted: member.muted,
  status_reason: member.status_reason ?? "",
});

export const messageRow = (message: ChatMessage): Row => ({ id: message.id, username: message.username, content: message.content, created_at: message.created_at });

const oneOf = (value: unknown, allowed: readonly string[], message: string): string => {
  if (typeof value === "string" && allowed.includes(value)) return value;
  throw new Error(message);
};

/** The request that makes a room what the form says (only what changed): Status is public (open to anyone) or private (the owner lets people in). */
export function changesOfRoom(changed: Row): RoomChanges {
  const { status, state, ...rest } = changed;
  const changes: Record<string, unknown> = { ...rest };
  if (status !== undefined) {
    const wanted = oneOf(status, ["public", "private"], tr("rm_e_status"));
    Object.assign(changes, wanted === "public" ? { visibility: "public", join_policy: "open" } : { join_policy: "approval" });
  }
  if (state !== undefined) changes.state = oneOf(state, ["open", "closed"], tr("rm_e_state"));
  return changes as RoomChanges;
}

/** The request that changes a member as the form says, and whether the room is handed over to them (the last thing done: it is the end of the owner's powers). */
export function changesOfMember(changed: Row): { body: { status?: "joined" | "banned"; reason?: string; muted?: boolean }; handOver: boolean } {
  const body: { status?: "joined" | "banned"; reason?: string; muted?: boolean } = {};
  let handOver = false;
  if (changed.role !== undefined) {
    handOver = oneOf(changed.role, ["member", "owner"], tr("rm_e_role")) === "owner"; // a member stays a member: only handing the room over changes a role
  }
  if (changed.status !== undefined) {
    body.status = oneOf(changed.status, ["joined", "banned"], tr("rm_e_member_status")) as "joined" | "banned";
    if (typeof changed.status_reason === "string") body.reason = changed.status_reason;
  }
  if (changed.muted !== undefined) body.muted = Boolean(changed.muted);
  return { body, handOver };
}
