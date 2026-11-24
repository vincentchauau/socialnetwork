import type { Metadata } from "next";
import type { ReactNode } from "react";
import AppFrame from "../chat/dock/AppFrame";
import "../chat/chatwork.css";
import "./werewolf.css";

export const metadata: Metadata = { title: "Werewolf · Social Network" };

/** The Werewolf (the home page, `/werewolf`, is itself a dock: it needs the open room to show its game, so it is excepted):  the game's css scoped under `.ww-app`; each page has its own column (see `WerewolfHome`, `WerewolfColumn`). Its rooms are rooms of the chat. */
export default function WerewolfLayout({ children }: { children: ReactNode }) {
  return (
    <AppFrame name="Werewolf" app="werewolf" css="app-werewolf app-chat" except={["/werewolf"]}>{children}</AppFrame>
  );
}
