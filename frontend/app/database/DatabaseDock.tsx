"use client";

import { type ReactNode, useMemo } from "react";

import GalleryView from "@sn/compounds/GalleryView";
import { autoGalleryConfig } from "@sn/compounds/galleryModel";
import type { ExtraPane } from "@sn/compounds/SplitPanel";
import Select from "@sn/elements/Select";
import { useSession } from "@sn/lib/useSession";
import { AppsMenuExtras, type AppsMenuGroup } from "@sn/compounds/appsMenuExtras";

import PageDock from "../chat/dock/PageDock";
import { appMainOf } from "../chat/dock/appMains";
import { libraryOf } from "../chat/dock/libraries";
import { DatabaseSelectionProvider, HOME_APP, type PlatformTable, adminApiOf, useDatabaseSelection } from "./selection";
import GridEditor from "./components/grid/GridEditor";
import { RefPickHost } from "./components/refs/refPick";

/** The label of the pane of the database tool: the table changed in place. */
const TABLE_PANE_LABEL = "Table";
/** The label of the pane of the same table as cards. */
const LIBRARY_PANE_LABEL = "Grid";
/** The label of the pane of the same table as lanes of cards, one lane for each value of a column. */
/** The label of the table chooser (the list of tables of the chosen app). */
const TABLE_CHOOSER_LABEL = "Choose table";

/** Apps with nothing in a table to pick, which the menu lists all the same: choosing one shows its own view as the page. */
const APPS_WITHOUT_TABLES = ["file", "center"]; // Users (the account) has its own view for everybody, not only for an admin
/** Not apps a person chooses: the accounts (the Center) and the agent that writes the words of the virtual people. Their tables are in the Database. */
const NOT_IN_APPS_MENU = new Set(["agent"]);
/** Apps whose view fills the page like a window (a split with its own scroll) instead of flowing down it. */
const FILLS_THE_PAGE = new Set(["file"]);

/** The same room around the table as the Database tool has around its own, so the views line up row for row. */
const PANE_PADDING = 16;

function Chosen({ children }: { children: (table: PlatformTable) => ReactNode }) {
  const selection = useDatabaseSelection();
  if (!selection?.table) return <p className="muted" style={{ margin: 0, padding: PANE_PADDING }}>{selection?.loading ? "…" : "—"}</p>;
  return <div style={{ padding: PANE_PADDING }}>{children(selection.table)}</div>;
}


/** The User panel of the app chosen in the Apps menu: the main page of that app. */
function UserView() {
  const selection = useDatabaseSelection();
  if (!selection) return null;
  if (selection.loading) return <p className="muted" style={{ margin: 0, padding: PANE_PADDING }}>…</p>;
  const app = selection.app;
  // An app with a main page (roulette, face, werewolf) shows it in this pane, scoped by its own class.
  const main = appMainOf(app);
  if (main) {
    const Main = main.component;
    // Full width of the pane, as the app shows on its own.
    // A dock (Chat, Werewolf) takes the height of its pane: without a height it would collapse to nothing.
    const dock = app === "chat" ? { height: "100%", minHeight: 480, display: "flex", flexDirection: "column" as const } : {};
    return <div className={main.className} style={{ padding: PANE_PADDING, width: "100%", boxSizing: "border-box", ...dock }}><Main /></div>;
  }
  // An app with a library of its own (the files) shows it; its data is not in the records.
  const Library = libraryOf(app);
  if (Library) return <Library />;
  // An app with no view of its own of the person's data shows one of its tables (the one picked last, else its first).
  const own = selection.tables.filter((table) => table.group === app);
  const table = selection.table?.group === app ? selection.table.name : own[0]?.name;
  const fill = FILLS_THE_PAGE.has(app);
  const frame = fill ? { height: "100%", boxSizing: "border-box", display: "flex", flexDirection: "column" } as const : {};
  const target = selection.table?.group === app ? selection.table : own[0];
  if (!target) return <p className="muted" style={{ margin: 0, padding: PANE_PADDING }}>—</p>;
  return <div style={{ padding: PANE_PADDING, ...frame }}><GridEditor key={`${target.database}/${target.name}`} api={adminApiOf(target.database)} table={target} /></div>;
}

/** Every table of every app, to pick the one Table, Grid and Board show (it sits under the buttons of the panes). */
function TableChooser({ shown }: { shown: string[] }) {
  const selection = useDatabaseSelection();
  if (!selection || selection.tables.length === 0 || shown.length === 0) return null; // the same table is the one of Database, Table, Grid and Board: the chooser is over all of them
  const value = selection.table ? `${selection.table.database}/${selection.table.name}` : "";
  const groups = [...new Set(selection.tables.map((table) => table.group ?? "other"))].sort((a, b) => a.localeCompare(b));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <Select
        aria-label={TABLE_CHOOSER_LABEL}
        value={value}
        onChange={(event) => {
          const [database, ...name] = event.target.value.split("/");
          selection.choose(database, name.join("/"));
        }}
        style={{ flex: "0 1 360px", minWidth: 0 }}
      >
        {groups.map((group) => (
          <optgroup key={group} label={group}>
            {selection.tables
              .filter((table) => (table.group ?? "other") === group)
              .map((table) => (
                <option key={`${table.database}/${table.name}`} value={`${table.database}/${table.name}`}>
                  {table.rows === undefined ? table.label : `${table.label} (${table.rows})`}
                </option>
              ))}
          </optgroup>
        ))}
      </Select>
    </div>
  );
}


/** The panes of the databases (the home page, for an admin): the tables of every app as a table, as cards and in lanes. */
const PLATFORM: ExtraPane[] = [
  // The table the admin picked, as a library of cards.
  { key: "grid", label: LIBRARY_PANE_LABEL, node: <Chosen>{(table) => <GridEditor key={`${table.database}/${table.name}`} api={adminApiOf(table.database)} table={table} />}</Chosen> },
];

/** What the Apps menu holds: the apps of the platform, to pick the one the views show. */
function MenuTables({ children }: { children: ReactNode }) {
  const selection = useDatabaseSelection();
  const groups = useMemo<AppsMenuGroup[] | null>(() => {
    if (!selection || selection.loading) return null;
    // The menu lists the apps only: the databases (the entry of the home page, whose key is empty) and each app, whose User panel is its main page.
    const keys = new Set<string>([...selection.tables.map((table) => table.group ?? "other"), ...APPS_WITHOUT_TABLES].filter((key) => !NOT_IN_APPS_MENU.has(key)));
    const apps = [...keys].sort((a, b) => a.localeCompare(b)).map((key) => ({ key, items: [], onSelectApp: () => selection.chooseApp(key), current: selection.app === key }));
    return [{ key: "", items: [], onSelectApp: () => selection.chooseApp(HOME_APP), current: selection.app === HOME_APP }, ...apps];
  }, [selection]);
  return <AppsMenuExtras.Provider value={groups}>{children}</AppsMenuExtras.Provider>;
}

/** The page of the dock: the databases for the home app, else the User panel of the app chosen in the Apps menu. */
const DOCK_APPS = new Set(["chat", "werewolf"]);

function Dock({ children, isAdmin }: { children: ReactNode; isAdmin: boolean }) {
  const selection = useDatabaseSelection();
  // Chat and Werewolf are docks already (their rooms, messages and members): shown alone, so there is no second Page | Chat bar.
  if (selection && selection.app !== HOME_APP && DOCK_APPS.has(selection.app)) return <UserView />;
  if (selection && selection.app !== HOME_APP) return <PageDock app="database" api={null}><UserView /></PageDock>;
  return <PageDock app="database" pageLabel={TABLE_PANE_LABEL} extraPanes={isAdmin ? PLATFORM : []} toolbar={(shown) => <TableChooser shown={shown} />}>{children}</PageDock>;
}

/** The dock of the Database app. The Apps menu picks what the page is: the databases (Database, Table, Grid and Board over the tables of every app) or an app's User panel. */
export default function DatabaseDock({ children, bar }: { children: ReactNode; bar?: ReactNode }) {
  const auth = useSession();
  const isAdmin = auth.status === "signed-in" && auth.user.group === "admin";
  return (
    <DatabaseSelectionProvider enabled={auth.status === "signed-in"} admin={isAdmin}>
      <MenuTables>{bar}</MenuTables>
      <RefPickHost>
        <Dock isAdmin={isAdmin}>{children}</Dock>
      </RefPickHost>
    </DatabaseSelectionProvider>
  );
}
