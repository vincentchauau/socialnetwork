"use client";

import { useEffect, useState } from "react";

import { shuffleTheme } from "../theme";
import CallsPanel from "./CallsPanel";
import DatabasePanel from "./DatabasePanel";
import FilesPanel from "./FilesPanel";
import NavBar, { View } from "./NavBar";

const VIEW_FROM_HASH: Record<string, View> = { "#file": "file", "#database": "database", "#calls": "calls" };

function Banner({ id }: { id: string }) {
  return (
    <header id={id} style={{ textAlign: "center" }}>
      <p>Tệp &amp; cơ sở dữ liệu · mỗi người dùng có thư mục và SQLite riêng.</p>
    </header>
  );
}

export default function WorkApp({ username, isAdmin }: { username: string; isAdmin: boolean }) {
  const [view, setView] = useState<View>("file");
  const [headerShown, setHeaderShown] = useState(false);

  // Like the original: a random theme on every load, header hidden at first.
  useEffect(() => {
    shuffleTheme();
    const fromHash = VIEW_FROM_HASH[window.location.hash];
    if (fromHash && (fromHash !== "calls" || isAdmin)) setView(fromHash);
  }, [isAdmin]);

  function changeView(next: View) {
    setView(next);
    window.history.replaceState(null, "", `#${next}`);
  }

  return (
    <>
      {headerShown && <Banner id="page-header" />}
      <main className="maxColumnContainer">
        <NavBar
          username={username}
          view={view}
          isAdmin={isAdmin}
          headerShown={headerShown}
          onToggleHeader={() => setHeaderShown(!headerShown)}
          onTheme={() => shuffleTheme()}
          onView={changeView}
        />
        {view === "file" && <FilesPanel />}
        {view === "database" && <DatabasePanel />}
        {view === "calls" && isAdmin && <CallsPanel />}
      </main>
      {headerShown && <Banner id="page-footer" />}
    </>
  );
}
