import type { ReactNode } from "react";

/** A page of one game (the room, the history): a scrolling column, the game's css under `.ww-app`. */
export default function WerewolfColumn({ children }: { children: ReactNode }) {
  return <main className="ww-app ww-page">{children}</main>;
}
