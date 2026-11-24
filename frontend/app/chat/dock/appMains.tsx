"use client";

import { type ComponentType, useState } from "react";
import dynamic from "next/dynamic";

import { useSession } from "@sn/lib/useSession";

import "../chatwork.css";
import "../../roulette/roulette.css";
import "../../face/face.css";
import "../../job/jobs.css";
import "../../werewolf/werewolf.css";
import "../../center/globals.css";
import "../../center/center.css";
import "@sn/lib/button.css";
import "@sn/lib/controls.css";
import "@sn/lib/plainButton.css";

import ChatDock from "./ChatDock";
import RoomCall from "../components/RoomCall";
import type { Room } from "../protocol";

/**
 * The main page of an app, shown in the User pane of the home page (the apps are not pages of their own any more).
 * `className` is the app's scope for its css (`app-<name>`, as in its layout), so the styles apply only inside the pane.
 * To add one: create the component, then add a line here.
 */
export interface AppMain {
  component: ComponentType;
  className: string;
}

const RouletteMain = dynamic(() => import("../../roulette/RouletteGame"));
const FaceMain = dynamic(() => import("../../face/components/FaceApp"));
const JobMain = dynamic(() => import("../../job/JobLibrary"));
const MarketMain = dynamic(() => import("../../market/MarketLibrary"));
const WerewolfHomeMain = dynamic(() => import("../../werewolf/components/WerewolfHome"));
const LoginFlowMain = dynamic(() => import("../../center/components/LoginFlow"));

/**
 * Chat as the other apps: the page on the left is the call of the open room; the dock on the right lists the rooms and the messages.
 * Picking a room in the dock opens it in the page.
 */
function ChatMain() {
  const auth = useSession();
  const [room, setRoom] = useState<Room | null>(null);
  if (auth.status !== "signed-in") return null;
  const page = room ? (
    <RoomCall key={room.slug} room={room} onClose={() => setRoom(null)} />
  ) : (
    <p className="muted" style={{ margin: 0, padding: 16 }}>Chọn một phòng ở danh sách / Pick a room from the list</p>
  );
  return <ChatDock app="chat" page={page} start={{ rooms: true, messages: false, members: false }} onRoom={setRoom} />;
}

/** Werewolf's home needs the signed-in person; it is shown only once the session is known. */
function WerewolfMain() {
  const auth = useSession();
  if (auth.status !== "signed-in") return null;
  return <WerewolfHomeMain user={auth.user} />;
}

const MAINS: Record<string, AppMain> = {
  roulette: { component: RouletteMain, className: "app-roulette" },
  face: { component: FaceMain, className: "app-face" },
  job: { component: JobMain, className: "app-jobs" },
  market: { component: MarketMain, className: "app-market" },
  werewolf: { component: WerewolfMain, className: "app-werewolf app-chat" },
  chat: { component: ChatMain, className: "app-chat" },
  center: { component: LoginFlowMain, className: "app-center antialiased" },
};

/** The main page of an app's API module, or undefined when it has none. */
export function appMainOf(api: string): AppMain | undefined {
  return Object.prototype.hasOwnProperty.call(MAINS, api) ? MAINS[api] : undefined;
}
