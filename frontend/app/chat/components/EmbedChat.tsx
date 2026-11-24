"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import "../chat.css";
import { chatApi } from "../api";
import { errorMessage } from "../errors";
import { type Room, readHash, slotsText } from "../protocol";
import AvatarImage from "./AvatarImage";
import { PEOPLE_CHANGED } from "./AddVirtual";
import DmRequest from "./DmRequest";
import JoinPrompt from "./JoinPrompt";
import MemberPanel from "./MemberPanel";
import PastRoom from "./PastRoom";
import RoomForm from "./RoomForm";
import RoomView from "./RoomView";
import RoomsPanel from "./RoomsPanel";
import Button from "@sn/elements/Button";
import Card from "@sn/elements/Card";
import SplitPanel, { type SplitPane } from "@sn/compounds/SplitPanel";
import { useT } from "@sn/locales";
import { tr } from "../i18n";

/** Which of the three parts of the chat are open: the rooms, the conversation, the people of the room. */
export interface Panels {
  rooms: boolean;
  members: boolean;
  messages: boolean;
}

/** The room that is open is remembered, so every app shows the same one until the person picks another. */
const ROOM_KEY = "sn_dock_room";
const ROOMS_WEIGHT = 5;
const MESSAGES_WEIGHT = 6;
const MEMBERS_WEIGHT = 4;
const ROOMS_MIN = 300;
const MESSAGES_MIN = 320;
const MEMBERS_MIN = 280;

const rememberedRoom = (): string | null => {
  try {
    return window.localStorage.getItem(ROOM_KEY);
  } catch {
    return null;
  }
};
const rememberRoom = (slug: string | null): void => {
  try {
    if (slug) window.localStorage.setItem(ROOM_KEY, slug);
    else window.localStorage.removeItem(ROOM_KEY);
  } catch {
    // not remembered: fine
  }
};

type Loaded = { status: "none" } | { status: "loading" } | { status: "missing"; text: string } | { status: "ready"; room: Room };

/** The form that is open where the conversation is: to make a room (changing one is the Edit form of its row). */
type Form = { open: true } | null;

interface Props {
  userId: number;
  username: string;
  panels: Panels;
  /** Where the buttons of the three parts (Rooms, Messages, Members) are over the chat: told what they are set to. Without it there are no buttons. */
  onPanels?: (next: Panels) => void;
  /** Told which room is open (null when none, or when I am not in it). */
  onRoom?: (room: Room | null) => void;
  /** Something needs the conversation (a private chat was opened, a form): the page turns Messages on. */
  onShowMessages?: () => void;
  /** The address bar says which room is open (`#room=<slug>`): on the page of the Chat. */
  syncHash?: boolean;
}

/**
 * The chat, the same everywhere (under every app and on the page of the Chat): one room, the same in every app, and three parts the page
 * turns on and off with its buttons, each one a table with the same bar over it (search, create) and the same actions on its rows:
 * Rooms, Messages (the conversation, with the answer to a request, the way into a room, the form of a room) and Members.
 */
export default function EmbedChat({ userId, username, panels, onPanels, onRoom, onShowMessages, syncHash = false }: Props) {
  const { t } = useT();
  const [slug, setSlug] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<Loaded>({ status: "none" });
  const [form, setForm] = useState<Form>(null);
  const [version, setVersion] = useState(0);
  const [roomsCount, setRoomsCount] = useState<number | null>(null);
  const [listVersion, setListVersion] = useState(0);
  const [live, setLive] = useState<{ online: ReadonlySet<number> | undefined; total: number | undefined; version: number }>({ online: undefined, total: undefined, version: 0 });
  const fromStorage = useRef(false);
  const slugNow = useRef<string | null>(null); // the room that is wanted now: an answer about another one is dropped

  // The room to open: the one in the address (an invitation link), else the one that was open last time.
  useEffect(() => {
    const sync = () => {
      const hash = readHash(window.location.hash);
      if (hash.room) {
        fromStorage.current = false;
        setSlug(hash.room);
      }
    };
    const hash = syncHash ? readHash(window.location.hash) : { room: null };
    if (hash.room) {
      setSlug(hash.room);
    } else {
      const last = rememberedRoom();
      fromStorage.current = last !== null;
      setSlug(last);
    }
    if (!syncHash) return;
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, [syncHash]);

  const fetchRoom = useCallback(async (wanted: string, quiet: boolean) => {
    if (!quiet) setLoaded({ status: "loading" });
    try {
      const room = await chatApi.room(wanted);
      if (slugNow.current !== wanted) return;
      if (fromStorage.current && room.me?.status !== "joined") {
        // the room of last time: opened again only when I am still in it
        fromStorage.current = false;
        setSlug(null);
        setLoaded({ status: "none" });
        rememberRoom(null);
        return;
      }
      fromStorage.current = false;
      setLoaded({ status: "ready", room });
    } catch (caught) {
      if (slugNow.current !== wanted) return;
      if (fromStorage.current) {
        fromStorage.current = false;
        setSlug(null);
        setLoaded({ status: "none" });
        return;
      }
      setLoaded({ status: "missing", text: errorMessage(caught) });
    }
  }, []);

  useEffect(() => {
    slugNow.current = slug;
    if (slug) void fetchRoom(slug, false);
    else setLoaded({ status: "none" });
  }, [slug, fetchRoom]);

  const select = useCallback(
    (next: string | null) => {
      fromStorage.current = false;
      setForm(null);
      setSlug(next);
      rememberRoom(next);
      if (syncHash) window.history.replaceState(null, "", next ? `#room=${encodeURIComponent(next)}` : window.location.pathname + window.location.search);
      if (next) onShowMessages?.();
    },
    [syncHash, onShowMessages],
  );

  const joinedRoom = loaded.status === "ready" && loaded.room.me?.status === "joined" ? loaded.room : null;
  const joinedSlug = joinedRoom?.slug;
  // The people of the room changed (somebody came, went, was muted, went online): the views beside the chat (the User pane) follow.
  useEffect(() => {
    if (joinedSlug) window.dispatchEvent(new CustomEvent(PEOPLE_CHANGED, { detail: { slug: joinedSlug } }));
  }, [joinedSlug, version, live]);
  useEffect(() => {
    onRoom?.(joinedRoom);
  }, [joinedRoom, onRoom]);

  const bumpList = () => setListVersion((value) => value + 1);
  const refresh = useCallback(() => {
    bumpList();
    setVersion((value) => value + 1);
    if (slug) void fetchRoom(slug, true);
  }, [slug, fetchRoom]);

  // The room as the server has it now (null: gone for this person: left, deleted).
  const setRoom = (next: Room | null) => {
    if (next === null) {
      bumpList();
      select(null);
      return;
    }
    setLoaded({ status: "ready", room: next });
    if (next.me === null) bumpList();
  };
  const opened = (room: Room) => {
    setLoaded({ status: "ready", room });
    select(room.slug);
    bumpList();
  };
  const saved = (room: Room) => {
    setForm(null);
    opened(room);
    bumpList();
  };
  const changedRoom = (room: Room) => {
    if (room.slug === slug) setLoaded({ status: "ready", room }); // the room that is open was changed: it stays open
    bumpList();
  };
  const openForm = () => {
    setForm({ open: true });
    onShowMessages?.();
  };

  async function write(otherId: number) {
    try {
      opened(await chatApi.openDm(otherId));
    } catch (caught) {
      setLoaded({ status: "missing", text: errorMessage(caught) });
    }
  }

  let pane;
  if (form) {
    pane = <RoomForm onSaved={saved} onCancel={() => setForm(null)} />;
  } else if (!slug || loaded.status === "none") {
    pane = (
      <div className="cw-centre">
        <Card stack style={{ alignItems: "center" }}>
          <h2 style={{ margin: 0 }}>{tr("rm_chao_mung_den_phong_chat")}</h2>
          <p role="status" style={{ margin: 0 }}>{tr("em_chon_mot_phong")}</p>
        </Card>
      </div>
    );
  } else if (loaded.status === "loading") {
    pane = <p role="status" className="cw-empty" style={{ textAlign: "center" }}>{tr("dang_tai")}</p>;
  } else if (loaded.status === "missing") {
    pane = (
      <div className="cw-centre">
        <Card stack style={{ alignItems: "center" }}>
          <p role="alert" style={{ margin: 0 }}>{loaded.text}</p>
          <Button type="button" variant="secondary" onClick={() => select(null)}>{tr("rm_ve_danh_sach_phong")}</Button>
        </Card>
      </div>
    );
  } else if (loaded.room.kind === "dm" && loaded.room.me?.status === "pending") {
    pane = (
      <DmRequest
        key={loaded.room.slug}
        room={loaded.room}
        myId={userId}
        onAnswered={(next) => {
          if (next === null) select(null);
          else setLoaded({ status: "ready", room: next });
          bumpList();
        }}
      />
    );
  } else if (loaded.room.state === "deleted" || loaded.room.me?.status === "left" || loaded.room.me?.status === "kicked") {
    pane = (
      <PastRoom
        key={loaded.room.slug}
        room={loaded.room}
        myId={userId}
        onChanged={(room) => {
          setLoaded({ status: "ready", room });
          bumpList();
        }}
        onGone={() => {
          select(null);
          bumpList();
        }}
      />
    );
  } else if (loaded.room.me?.status === "joined") {
    pane = <RoomView key={loaded.room.slug} room={loaded.room} myId={userId} username={username} onRoom={setRoom} onRefresh={refresh} onLive={setLive} />;
  } else {
    pane = (
      <JoinPrompt
        key={loaded.room.slug}
        room={loaded.room}
        onJoined={(room) => {
          setRoom(room);
          bumpList();
        }}
      />
    );
  }

  const showMembers = panels.members && joinedRoom !== null;
  const split: SplitPane[] = [
    {
      key: "rooms",
      label: onPanels ? `${t("dock.rooms")}${roomsCount !== null ? ` (${roomsCount})` : ""}` : undefined,
      weight: ROOMS_WEIGHT,
      minSize: ROOMS_MIN,
      node: !panels.rooms ? null : <RoomsPanel selected={form ? null : slug} onSelect={select} onCreate={openForm} onRoomChanged={changedRoom} listVersion={listVersion} onFirstRoom={syncHash ? select : undefined} onCount={setRoomsCount} />,
    },
    {
      key: "messages",
      label: onPanels ? t("dock.messages") : undefined,
      weight: MESSAGES_WEIGHT,
      minSize: MESSAGES_MIN,
      node: !panels.messages ? null : <div className="cw-pane-wrap" style={{ height: "100%" }}>{pane}</div>,
    },
    {
      key: "members",
      label: onPanels ? `${t("dock.members")}${joinedRoom ? ` (${joinedRoom.members})` : ""}` : undefined,
      weight: MEMBERS_WEIGHT,
      minSize: MEMBERS_MIN,
      node: joinedRoom ? <MemberPanel room={joinedRoom} myId={userId} version={version + live.version} onlineIds={live.online} onWrite={(otherId) => void write(otherId)} onChanged={refresh} /> : null,
    },
  ];
  const visible = { rooms: panels.rooms, messages: panels.messages, members: showMembers };
  const shownNone = !panels.rooms && !panels.messages && !showMembers;
  return (
    <div className="cw-app cw-embed" style={{ height: "100%", padding: 8, boxSizing: "border-box" }}>
      <SplitPanel
        panes={split}
        header={joinedRoom ? (
          <>
            <AvatarImage url={joinedRoom.avatar} name={joinedRoom.title} size={28} />
            <h2 className="cw-room-title" style={{ margin: 0, fontSize: "0.95rem" }}>{joinedRoom.visibility === "private" ? "🔒 " : ""}{joinedRoom.title}</h2>
            <span className="muted" style={{ fontSize: 13 }}>{slotsText(joinedRoom)} · {tr("rm_p0_truc_tuyen", { p0: live.total ?? live.online?.size ?? 0 })}</span>
          </>
        ) : null}
        label={t("dock.title")}
        resizeLabel={tr("em_keo_de_doi_kich_thuoc")}
        visible={visible}
        onVisibleChange={(next) => onPanels?.({ rooms: next.rooms === true, messages: next.messages === true, members: next.members === true })}
      />
      {shownNone && !onPanels && <p className="cw-empty">{tr("em_dong")}</p>}
    </div>
  );
}
