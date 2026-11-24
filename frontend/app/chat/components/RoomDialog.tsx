"use client";

import { useRef } from "react";

import { chatApi } from "../api";
import type { Room } from "../protocol";
import RowDialog from "./RowDialog";
import { ROOM_TABLE, changesOfRoom, roomRow } from "./rowTables";

interface Props {
  room: Room;
  onSaved: (room: Room) => void;
  onClose: () => void;
}

/** "Edit row" for a room: only its owner opens it, and what is saved goes through the same call as before (the server keeps the rules). */
export default function RoomDialog({ room, onSaved, onClose }: Props) {
  const row = useRef(roomRow(room)).current;
  return <RowDialog table={ROOM_TABLE} row={row} onClose={onClose} onSave={async (changed) => onSaved(await chatApi.update(room.slug, changesOfRoom(changed)))} />;
}
