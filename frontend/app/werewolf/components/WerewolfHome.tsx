"use client";

import { useCallback, useEffect, useState } from "react";

import type { User } from "@sn/api";
import Button from "@sn/elements/Button";
import { TabPanel } from "@sn/compounds/SplitPanel";

import ChatDock from "../../chat/dock/ChatDock";
import { errorMessage } from "../../chat/errors";
import type { Room } from "../../chat/protocol";
import { MEMBERS_CHANGED } from "../../chat/components/AddVirtual";
import { prepareGame } from "../../chat/werewolf";
import HistoryView from "./HistoryView";
import Leaderboard from "./Leaderboard";
import RoomView from "./RoomView";
import { tr } from "../i18n";

/** The channel of the Werewolf: its rooms are the rooms of the chat in the dock (the category `werewolf`). */
const WEREWOLF_APP = "werewolf";

/** The game of the room that is open in the dock: not started until someone asks, then the lobby (the roles, the bots) and the game. */
export function GameOfRoom({ room }: { room: Room }) {
  const [game, setGame] = useState<{ code: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const joined = room.me?.status === "joined" && room.state === "open" && room.kind !== "dm"; // a private chat has no game
  const play = useCallback(async () => {
    setBusy(true);
    setProblem(null);
    try {
      setGame(await prepareGame(room.slug));
    } catch (caught) {
      setProblem(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }, [room.slug]);

  // Every room has one game: the page shows it as soon as the room is open (made the first time, the seats follow the room after).
  useEffect(() => {
    setGame(null);
    setProblem(null);
    if (joined) void play();
  }, [room.slug, joined, play]);

  // Virtual people came into the room: the seats of its game follow (asking for the game again does it; the people in it see the change).
  useEffect(() => {
    if (!game) return;
    const follow = (event: Event) => {
      if ((event as CustomEvent<{ slug: string }>).detail?.slug !== room.slug) return;
      // The room may have a new game now (sending someone away changes the code, so they cannot use the old one): follow it.
      void prepareGame(room.slug, true).then((next) => setGame((current) => (current?.code === next.code ? current : next)), () => undefined);
    };
    window.addEventListener(MEMBERS_CHANGED, follow);
    return () => window.removeEventListener(MEMBERS_CHANGED, follow);
  }, [game, room.slug]);

  if (game) return <RoomView key={game.code} code={game.code} onExit={() => setGame(null)} hideRules />;
  return (
    <section className="card stack ww-center" aria-label={tr("ww_van_cua_phong")}>
      <h2>{room.title}</h2>
      <p className="muted">{tr("ww_moi_phong_mot_van")}</p>
      {!joined ? (
        <p className="muted">{tr("ww_vao_phong_de_choi")}</p>
      ) : busy ? (
        <p role="status" className="muted">{tr("dang_tai_phong")}</p>
      ) : (
        <div className="ww-center">
          <Button type="button" onClick={() => void play()} style={{ flex: "0 0 auto" }}>
            🐺 {tr("ww_choi_ma_soi_o_phong_nay")}
          </Button>
        </div>
      )}
      {problem && <p role="alert" className="error">{problem}</p>}
    </section>
  );
}

/**
 * The Werewolf, like every app: the page with the game, and the chat of the app under it (Rooms, Members, Messages; the rooms of the
 * Werewolf are the rooms of the chat). The game is the one of the room that is open in the chat; its lobby is where the host deals the roles.
 */
export default function WerewolfHome(_props: { user: User }) {
  const [room, setRoom] = useState<Room | null>(null);
  const onRoom = useCallback((next: Room | null) => setRoom(next), []);

  return (
    <ChatDock app={WEREWOLF_APP} api="werewolf" start={{ rooms: true, members: true, messages: true }} onRoom={onRoom} page={
      <main className="ww-app ww-page">
        <section className="ww-box stack ww-center" aria-label={tr("ma_soi")}>
          <header className="ww-hero">
            <span className="ww-big" aria-hidden="true">🐺</span>
            <h1>{tr("ma_soi")}</h1>
          </header>
          <TabPanel
            aria-label={tr("ma_soi")}
            data={[
              { key: "game", label: tr("tab_game") },
              { key: "history", label: tr("tab_history") },
              { key: "leaderboard", label: tr("tab_leaderboard") },
            ]}
            panels={{
              game: room ? <GameOfRoom room={room} /> : <section className="card stack ww-center" aria-label={tr("ww_chon_hoac_tao_phong")}><h2>{tr("ww_chon_hoac_tao_phong")}</h2><ol className="ww-steps">{["ww_buoc_1", "ww_buoc_2", "ww_buoc_3", "ww_buoc_4"].map((key) => <li key={key}>{tr(key)}</li>)}</ol></section>,
              history: <HistoryView embedded />,
              leaderboard: <Leaderboard />,
            }}
          />
        </section>
      </main>
    } />
  );
}
