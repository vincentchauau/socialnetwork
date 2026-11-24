"use client";

import { type ReactNode, createContext, useContext, useEffect, useMemo, useState } from "react";

import { apiFetch } from "@sn/api";
import { APPS } from "@sn/lib/apps";
import type { TableInfo } from "@sn/compounds/crudModel";

/** Apps that are listed but have no tables to ask for: the files (a tree of folders) and the Database (the home, `/`, which is no module of its own). */
const NO_TABLES = new Set(["file", "database"]);

/** The apps whose backend has an admin API (center and every app of the menu that has a backend): the page asks each one. */
export const ADMIN_MODULES: readonly string[] = [
  "center",
  ...APPS.map((app) => app.href.slice(1)).filter((name) => name !== "" && !NO_TABLES.has(name)),
];


const STORAGE_KEY = "sn_database_selection";

/** The base of the one address of an app's tables (for an admin: every row, by the rules of each table; the same engine as a person's own rows). */
export const adminApiOf = (module: string) => `/api/${module}/records`;

/** The app that is the home page: the databases (Database, Table, Grid and Board over the tables of every app). Any other app shows its own User panel. */
export const HOME_APP = "database";

/** A table of the description plus the app it belongs to (`database` is that app: the one address of its tables is `/api/<app>/records`). */
export type PlatformTable = TableInfo & { database: string; rows?: number; group?: string };

/** What an admin picked: one table of the app databases. The views of the Database app (Database, Table, Library) all show this one table. */
interface DatabaseSelection {
  /** An admin picks among the tables of the app databases; anyone else among the tables of the apps they may change themselves (`/records`, their own rows). */
  admin: boolean;
  /** Every table of every database, grouped by app in the chooser. */
  tables: PlatformTable[];
  table: PlatformTable | null;
  /** The app chosen in the Apps menu: `HOME_APP` (the databases) or an app, whose User panel is then the main page. */
  app: string;
  chooseApp: (app: string) => void;
  /** The databases are still being asked for. */
  loading: boolean;
  choose: (database: string, name: string) => void;
}

const Context = createContext<DatabaseSelection | null>(null);

/** The selection of the Database app, or null outside of it (the tool then keeps its own choosers). */
export function useDatabaseSelection(): DatabaseSelection | null {
  return useContext(Context);
}

function remembered(): { database?: string; table?: string } {
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}") as { database?: string; table?: string };
  } catch {
    return {};
  }
}

/** Asks which databases there are and what tables each has, and keeps the table chosen (the last choice is remembered). */
export function DatabaseSelectionProvider({ enabled, admin, children }: { enabled: boolean; admin: boolean; children: ReactNode }) {
  const [tables, setTables] = useState<PlatformTable[] | null>(null);
  const [chosen, setChosen] = useState<{ database: string; table: string } | null>(null);
  const [app, setApp] = useState<string>(HOME_APP);
  // An address such as /?app=center (the account, from /user) opens that app in the User pane.
  useEffect(() => {
    const asked = new URLSearchParams(window.location.search).get("app");
    if (asked) setApp(asked);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const loadAdmin = () =>
      Promise.all(
        ADMIN_MODULES.map((module) =>
          apiFetch<TableInfo[]>(`${adminApiOf(module)}/tables`).then(
            (list) => (Array.isArray(list) ? list.map((table) => ({ ...table, database: module, group: module }) as PlatformTable) : []),
            () => [] as PlatformTable[], // a module that has no tables to show, or one that is down
          ),
        ),
      );
    const loadMine = () =>
      Promise.all(
        ADMIN_MODULES.map((module) =>
          apiFetch<TableInfo[]>(`/api/${module}/records/tables`).then(
            (list) => (Array.isArray(list) ? list.map((table) => ({ ...table, database: module, group: module }) as PlatformTable) : []),
            () => [] as PlatformTable[], // a module with no tables of the person's own, or one that is down
          ),
        ),
      );
    (admin ? loadAdmin() : loadMine())
      .then((lists) => {
        if (cancelled) return;
        setTables(lists.flat());
        const last = remembered();
        if (last.database && last.table) setChosen({ database: last.database, table: last.table });
      })
      .catch(() => !cancelled && setTables([]));
    return () => {
      cancelled = true;
    };
  }, [enabled, admin]);

  const value = useMemo<DatabaseSelection | null>(() => {
    if (!enabled) return null;
    const all = tables ?? [];
    const found = all.find((candidate) => candidate.database === chosen?.database && candidate.name === chosen?.table);
    const table = found ?? all[0] ?? null;
    const choose = (database: string, name: string) => {
      setChosen({ database, table: name });
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ database, table: name }));
      } catch {
        // not remembered: fine
      }
    };
    return {
      app,
      // An app is picked in the Apps menu: the databases (the home page) or an app, whose User panel is the main page.
      chooseApp: setApp,
      admin,
      tables: all,
      table,
      loading: tables === null,
      choose,
    };
  }, [enabled, admin, tables, chosen, app]);

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

/** The address of the table a reference points to: the records of the app that owns that table (the users are in the center),
 * or the address given when no app owns it. */
export function useRefApi(tableName: string | undefined, fallback: string): string {
  const selection = useDatabaseSelection();
  const owner = tableName ? selection?.tables.find((table) => table.name === tableName) : undefined;
  return owner ? adminApiOf(owner.database) : fallback;
}
