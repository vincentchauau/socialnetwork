"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import SiteBar from "@sn/complex/SiteBar";
import PageDock from "./PageDock";

/**
 * The frame of every app: its class, the site bar, and the page dock with the page in <main>. Every layout is this frame, so the apps look and
 * behave the same. `css` is the app's class (app-<name>, scoped styles); `except` lists the addresses that show without the dock; `api` is passed
 * on to the dock (null: the page alone, no table panes).
 */
export default function AppFrame({ name, app, css, api, except, children }: { name: string; app: string; css: string; api?: string | null; except?: string[]; children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className={`${css} sn-frame`}>
      <SiteBar name={name} href={pathname} />
      <PageDock app={app} api={api} except={except}>
        <main>{children}</main>
      </PageDock>
    </div>
  );
}
