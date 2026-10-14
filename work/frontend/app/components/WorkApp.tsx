"use client";

import { useState } from "react";

import CallsPanel from "./CallsPanel";
import DatabasePanel from "./DatabasePanel";
import FilesPanel from "./FilesPanel";

type Tab = "files" | "db" | "calls";

export default function WorkApp({ isAdmin }: { isAdmin: boolean }) {
  const [tab, setTab] = useState<Tab>("files");
  const tabs: { id: Tab; label: string }[] = [
    { id: "files", label: "Tệp" },
    { id: "db", label: "Cơ sở dữ liệu" },
    ...(isAdmin ? [{ id: "calls" as const, label: "Cuộc gọi" }] : []),
  ];
  return (
    <div className="stack">
      <h1>Tệp &amp; cơ sở dữ liệu</h1>
      <div role="tablist" aria-label="Khu vực làm việc" className="row work-tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            className={tab === t.id ? undefined : "secondary"}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "files" && <FilesPanel />}
        {tab === "db" && <DatabasePanel />}
        {tab === "calls" && isAdmin && <CallsPanel />}
      </div>
    </div>
  );
}
