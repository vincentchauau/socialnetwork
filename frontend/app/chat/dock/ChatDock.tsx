"use client";

import { type ComponentType, type ReactNode, useEffect, useState } from "react";
import { usePathname } from "next/navigation";

import EmbedChat, { type Panels } from "../components/EmbedChat";
import type { Room } from "../protocol";
import { libraryEntryOf, libraryOf, isLibraryHome } from "./libraries";
import { crudTr } from "@sn/compounds/CrudView";
import SplitPanel, { type ExtraPane, type SplitPane, type SplitToolbar } from "@sn/compounds/SplitPanel";
import { BORDER } from "@sn/lib/theme";
import { useFramed } from "@sn/lib/hooks";
import { useSession } from "@sn/lib/useSession";
import { useT } from "@sn/locales";

const STORAGE_PREFIX = "sn_dock_";
const SPLIT_MIN_PX = 160; // neither the page nor the chat is ever squeezed below this
const PAGE_WEIGHT = 11;
const CHAT_WEIGHT = 9;
const START: Panels = { rooms: false, members: false, messages: true };

function remembered(app: string, start: Panels): Panels {
  try {
    const raw = window.localStorage.getItem(STORAGE_PREFIX + app);
    const saved = raw ? (JSON.parse(raw) as Partial<Panels>) : null;
    if (saved) return { rooms: saved.rooms === true, members: saved.members === true, messages: saved.messages !== false };
  } catch {
    // no storage (private window): the page starts as it always does
  }
  return start;
}

/** The label of the library pane. */
const LIBRARY_LABEL = "Grid";

/** The panes of an app beside its page: the page, its library (when it has one) and the extra panes (hidden unless asked for). */
export function appPanes(page: ReactNode, pageLabel: string | undefined, Library: ComponentType | undefined, extra: readonly ExtraPane[]): SplitPane[] {
  return [
    { key: "page", label: pageLabel, node: <div style={{ minHeight: "100%", display: "flex", flexDirection: "column" }}>{page}</div>, keepMounted: true, defaultVisible: true, weight: 3 },
    ...(Library ? [{ key: "library", label: LIBRARY_LABEL, node: <Library />, keepMounted: true, defaultVisible: true, weight: 3 } satisfies SplitPane] : []),
    ...extra.map((pane): SplitPane => ({ key: pane.key, label: pane.label, title: pane.title, node: pane.node, defaultVisible: pane.defaultVisible ?? false, weight: 3 })),
  ];
}

/**
 * The chat room of an app, under the page of the app: two split panels: the page and the chat (buttons Page and Chat), and in the chat three buttons that open and close what is in it, one by one. Rooms is the list
 * of the rooms of this app, Members is who is in the room that is open, and Messages is sending and receiving. The chat is the same
 * component the Chat page uses (no frame). A button that is off closes that part for good: with Messages off nothing is sent or
 * received. Needs a signed-in person (it shows nothing otherwise). `start`: the parts that are open the first time (later: as the person left them);
 * `onRoom`: told which room is open; `api`: the API module of the app, when given the page also gets the library and extra panes (TablePanels).
 */
export default function ChatDock({ app, start = START, onRoom, fill = false, page, api, extraPanes, pageLabel, toolbar }: { app: string; api?: string; extraPanes?: ExtraPane[]; pageLabel?: string; toolbar?: SplitToolbar; start?: Panels; onRoom?: (room: Room | null) => void; fill?: boolean; page?: ReactNode }) {
  const { t } = useT();
  const auth = useSession();
  const pathname = usePathname();
  const [panels, setPanels] = useState<Panels>(start);
  const framed = useFramed();

  const libEntry = api ? libraryEntryOf(api) : undefined;
  const isLibHome = libEntry && isLibraryHome(pathname, libEntry.home);
  const Library = isLibHome ? libEntry.component : undefined;

  const withTables = page && api && !isLibHome ? (
    <div style={{ height: "100%", minHeight: 0, display: "flex", flexDirection: "column" }}>
      <SplitPanel panes={appPanes(page, pageLabel, libraryOf(api), extraPanes ?? [])} label={crudTr("tables")} storageKey={`sn_tables_${api}`} toolbar={toolbar} />
    </div>
  ) : page;
  const any = panels.rooms || panels.members || panels.messages;

  useEffect(() => {
    setPanels(remembered(app, start));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app]);

  if (auth.status !== "signed-in" || (framed && page)) return page ? <div style={{ height: "100%", overflow: "auto" }}>{page}</div> : null;

  if (Library) {
    return (
      <div style={{ height: "100%", minHeight: 0, overflow: "hidden" }}>
        <main style={{ height: "100%", boxSizing: "border-box", display: "flex", flexDirection: "column", overflow: "auto" }}>
          <Library />
        </main>
      </div>
    );
  }

  const choose = (next: Panels) => {
    setPanels(next);
    try {
      window.localStorage.setItem(STORAGE_PREFIX + app, JSON.stringify(next));
    } catch {
      // not remembered: fine
    }
  };

  const chat = (
    <div className="app-chat" style={{ height: "100%" }}>
      <EmbedChat userId={auth.user.id} username={auth.user.username} panels={panels} onPanels={choose} onRoom={onRoom} onShowMessages={() => setPanels((current) => ({ ...current, messages: true }))} syncHash={fill} />
    </div>
  );
  if (!page) return <section aria-label={t("dock.title")} style={{ flex: "1 1 0", minHeight: 0, display: "flex", flexDirection: "column", background: "var(--solid-0)" }}>{chat}</section>;
  return (
    <SplitPanel
      orientation="vertical"
      label={t("dock.title")}
      resizeLabel={t("dock.resize")}
      storageKey={`${STORAGE_PREFIX}${app}_split`}
      panes={[
        { key: "page", label: t("dock.page"), node: <div style={{ height: "100%", minHeight: 0, display: "flex", flexDirection: "column" }}>{withTables}</div>, keepMounted: true, weight: PAGE_WEIGHT, minSize: SPLIT_MIN_PX },
        { key: "chat", label: t("dock.chat"), node: chat, weight: CHAT_WEIGHT, minSize: SPLIT_MIN_PX, fit: !any },
      ]}
    />
  );
}
