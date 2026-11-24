"use client";

import { useState } from "react";

import { chatApi } from "../api";
import { errorMessage } from "../errors";
import { type Room, stateText } from "../protocol";
import Alert from "@sn/elements/Alert";
import Button from "@sn/elements/Button";
import Card from "@sn/elements/Card";
import { tr } from "../i18n";

interface Props {
  room: Room;
  onJoined: (room: Room) => void;
}

/** What a room shows to someone who is not in it yet: who it is for, and the way in (or why there is none). */
export default function JoinPrompt({ room, onJoined }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const status = room.me?.status ?? null;
  const unavailable = stateText(room.state);

  async function join() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      onJoined(await chatApi.join(room.slug));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function withdraw() {
    setBusy(true);
    try {
      await chatApi.leave(room.slug);
      onJoined({ ...room, me: null });
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cw-centre">
      <Card stack style={{ alignItems: "center", textAlign: "center" }}>
        <h2 style={{ margin: 0 }}>{room.title}</h2>
        <p className="cw-room-sub" style={{ margin: 0 }}>
          {tr("rm_p0_thanh_vien", { p0: room.members })}
          {room.category ? ` · ${room.category}` : ""}
        </p>
        {status === "pending" ? (
          <>
            <p role="status">{tr("rm_yeu_cau_dang_cho_duyet")}</p>
            <Button type="button" variant="secondary" disabled={busy} onClick={() => void withdraw()}>
              {tr("rm_rut_yeu_cau")}
            </Button>
          </>
        ) : status === "banned" ? (
          <p role="status">{tr("rm_ban_bi_chan")}</p>
        ) : unavailable ? (
          <p role="status">{unavailable}</p>
        ) : (
          <>
            <Button type="button" loading={busy} loadingLabel={tr("dang_xu_ly")} onClick={() => void join()}>
              {room.join_policy === "approval" ? tr("rm_xin_vao_phong") : tr("rm_vao_phong")}
            </Button>
          </>
        )}
        <Alert>{error}</Alert>
      </Card>
    </div>
  );
}
