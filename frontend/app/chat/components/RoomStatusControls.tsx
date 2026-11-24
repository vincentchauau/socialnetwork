"use client";

import { useState } from "react";

import { chatApi } from "../api";
import { errorMessage } from "../errors";
import type { Room } from "../protocol";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";

interface Props {
  room: Room;
  /** The room as the server has it after the change. */
  onRoom: (room: Room) => void;
}

/** What only the owner of a room (or the one who started a chat of two) does to it as a whole at a click: close it, or open it again (everything else is in Edit). */
export default function RoomStatusControls({ room, onRoom }: Props) {
  const [error, setError] = useState<string | null>(null);
  if (room.me?.role !== "owner" || room.me.status !== "joined") return null;
  const closed = room.state === "closed";

  async function toggle() {
    setError(null);
    try {
      onRoom(await chatApi.update(room.slug, { state: closed ? "open" : "closed" }));
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <>
      <Button type="button" size="sm" variant={closed ? "primary" : "secondary"} title={error ?? undefined} onClick={() => void toggle()}>
        {closed ? tr("rm_mo_lai_phong") : tr("rm_dong_phong")}
      </Button>
      {error && <span role="alert" className="cw-room-sub">{error}</span>}
    </>
  );
}
