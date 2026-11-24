"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import type { SplitToolbar } from "@sn/compounds/SplitPanel";
import type { ExtraPane } from "@sn/compounds/SplitPanel";
import type { Room } from "../protocol";
import ChatDock from "./ChatDock";

/** The app names that differ from the name of their API module; apps with no module (admin) are not here and get no library. */
const API_OF: Record<string, string> = { jobs: "job" };
const NO_API = new Set(["admin"]);

/** The dock of an app whose pages are several, except where the page is the chat itself. `api` null: the page alone, with no table panes beside it. */
export default function PageDock({ app, except = [], children, api, extraPanes, pageLabel, onRoom, toolbar }: { app: string; except?: string[]; children: ReactNode; api?: string | null; extraPanes?: ExtraPane[]; pageLabel?: string; onRoom?: (room: Room | null) => void; toolbar?: SplitToolbar }) {
  const pathname = usePathname();
  // An entry ending with "/" covers every page below it (a detail page such as /market/products/<id>).
  const alone = except.some((entry) => (entry.endsWith("/") ? pathname.startsWith(entry) : pathname === entry));
  if (alone) return <div className="sn-alone" style={{ flex: "1 1 0", minHeight: 0, display: "flex", flexDirection: "column", overflow: "auto" }}>{children}</div>;
  return <ChatDock app={app} api={api === null ? undefined : (api ?? (NO_API.has(app) ? undefined : (API_OF[app] ?? app)))} page={children} extraPanes={extraPanes} pageLabel={pageLabel} onRoom={onRoom} toolbar={toolbar} />;
}
