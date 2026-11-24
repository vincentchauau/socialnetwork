import type { Metadata } from "next";
import type { ReactNode } from "react";
import DatabaseDock from "./DatabaseDock";
import SiteBar from "@sn/complex/SiteBar";
import "../chat/chatwork.css";

export const metadata: Metadata = { title: "Database · Social Network" };

// The home page: the same frame as every app (app-<name> sn-frame, the bar, the dock), with the Database's own dock inside.
export default function DatabaseLayout({ children }: { children: ReactNode }) {
  return (
    <div className="app-chat sn-frame">
      <DatabaseDock bar={<SiteBar name="Database" href="/" />}>{children}</DatabaseDock>
    </div>
  );
}
