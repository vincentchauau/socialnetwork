"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type { User } from "@sn/api";

import { useCommand } from "../hooks/useCommand";
import { useToast } from "../hooks/useToast";
import { werewolfApi } from "../lib/api";
import { errorText } from "../lib/errors";
import { isValidCode, normalizeCode, ROOM_CODE_LENGTH } from "../lib/setup";
import type { CreateBody, SetupMeta } from "../lib/types";
import FieldLabel from "./FieldLabel";
import HelpSheet from "./HelpSheet";
import RoomList from "./RoomList";
import SetupForm from "./SetupForm";
import Toast from "./Toast";

/** Home: create a room, join by code, public rooms, history link. */
export default function HomeView({ user }: { user: User }) {
  const router = useRouter();
  const { message, notify, dismiss } = useToast();
  const { busy, run } = useCommand(notify);
  const [meta, setMeta] = useState<SetupMeta | null>(null);
  const [joinCode, setJoinCode] = useState("");

  useEffect(() => {
    werewolfApi
      .meta()
      .then(setMeta)
      .catch((e: unknown) => notify(errorText(e)));
  }, [notify]);

  const enter = (id: string) => router.push(`/room/${encodeURIComponent(id)}`);

  const create = (body: CreateBody) =>
    void run(async () => {
      const room = await werewolfApi.create(body);
      enter(room.id);
    });

  const join = (code: string) =>
    void run(async () => {
      const room = await werewolfApi.join(code);
      enter(room.id);
    });

  const joinValid = isValidCode(joinCode);

  return (
    <div className="stack ww-home">
      <header className="ww-hero">
        <span className="ww-big" aria-hidden="true">
          🐺
        </span>
        <h1>Ma Sói</h1>
        <p className="muted">
          Xin chào, <strong>{user.username}</strong>. 🧑 Người · 🐺 Sói · 👻 Ma
        </p>
        <div className="row ww-wrap ww-center">
          <HelpSheet meta={meta} />
          <Link href="/history" className="ww-link-button">
            📜 Lịch sử ván chơi
          </Link>
          <a href="/" className="ww-link-button">
            ← Trang chủ
          </a>
        </div>
      </header>

      <section className="card stack" aria-labelledby="ww-join-title">
        <h2 id="ww-join-title">🔑 Vào phòng bằng mã</h2>
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            if (joinValid) join(joinCode);
          }}
        >
          <FieldLabel htmlFor="ww-join-code" text="Mã phòng" hint={`(${ROOM_CODE_LENGTH} chữ cái)`} />
          <div className="row">
            <input
              id="ww-join-code"
              value={joinCode}
              maxLength={ROOM_CODE_LENGTH}
              autoCapitalize="characters"
              placeholder="ABCDE"
              onChange={(event) => setJoinCode(normalizeCode(event.target.value))}
            />
            <button type="submit" disabled={busy || !joinValid}>
              Vào phòng
            </button>
          </div>
        </form>
      </section>

      <RoomList busy={busy} onJoin={join} />

      {meta ? (
        <SetupForm meta={meta} username={user.username} busy={busy} notify={notify} onCreate={create} />
      ) : (
        <p className="muted">Đang tải cấu hình…</p>
      )}
      <Toast message={message} onClose={dismiss} />
    </div>
  );
}
