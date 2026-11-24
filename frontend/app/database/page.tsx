"use client";

import { useEffect } from "react";

import { AuthGate } from "@sn/compounds/AuthGate";
import TableEditor from "./components/table/TableEditor";

import { tr } from "./i18n";
import { adminApiOf, useDatabaseSelection } from "./selection";
import { useSession } from "@sn/lib/useSession";

function DatabaseBody() {
  const selection = useDatabaseSelection(); // present for an admin: the tables are shown by the Table, Grid and Board panes above
  const table = selection?.table;
  if (!table) return <p className="muted" style={{ margin: 0, padding: 16 }}>{selection?.loading ? "…" : "—"}</p>;
  return (
    <div style={{ padding: 16 }}>
      <TableEditor key={`${table.database}/${table.name}`} api={adminApiOf(table.database)} table={table} database={table.database} />
    </div>
  );
}

export default function DatabasePage() {
  const session = useSession();
  useEffect(() => {
    if (session.status === "anonymous") window.location.assign("/user"); // the home page is for people who signed in
  }, [session.status]);
  return (
    <AuthGate title={tr("co_so_du_lieu")}>
      {(user) => (
        <main className="maxColumnContainer">
          <DatabaseBody />
        </main>
      )}
    </AuthGate>
  );
}
