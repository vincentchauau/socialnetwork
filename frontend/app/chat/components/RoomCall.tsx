"use client";

import { useState } from "react";

import { type Meeting, meetingApi } from "../api";
import { errorMessage } from "../errors";
import { type Room, isOwner } from "../protocol";
import CallRoom from "./CallRoom";
import { tr } from "../i18n";
import Alert from "@sn/elements/Alert";

interface Props {
  room: Room;
  onClose: () => void;
}

/**
 * The call of a room, opened from the room's header: it starts (or joins) the room's one meeting, then shows the call. The owner can end it for
 * everybody; leaving only closes the call on this side.
 */
export default function RoomCall({ room, onClose }: Props) {
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  // Before the call the page shows the checks (camera, microphone) and the Join button; the meeting starts only when the person joins.
  async function join() {
    setBusy(true);
    try {
      setMeeting(await meetingApi.start(room.slug));
      setProblem("");
    } catch (failure) {
      setProblem(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  async function end() {
    try {
      await meetingApi.end(room.slug);
    } catch (failure) {
      setProblem(errorMessage(failure));
      return;
    }
    onClose();
  }

  return (
    <section aria-label={room.title} style={{ display: "flex", flexDirection: "column", gap: 8, padding: 8, height: "100%", minHeight: 460, width: "100%", minWidth: 0, boxSizing: "border-box" }}>
      {problem ? <Alert tone="error">{problem}</Alert> : null}
      <CallRoom
        meeting={meeting}
        virtualPeople={[]}
        canEnd={isOwner(room.me)}
        onLeave={onClose}
        onEnd={() => void end()}
        onJoin={() => void join()}
        joinLabel={busy ? "…" : tr("rm_tham_gia")}
        joinDisabled={busy}
      />
    </section>
  );
}
