import type { ReactNode } from "react";
import AppFrame from "../chat/dock/AppFrame";
import OneTimeNotices from "./components/OneTimeNotices";
import "./globals.css";
import "./center.css";
import "@sn/lib/button.css";
import "@sn/lib/controls.css";
import "@sn/lib/plainButton.css";

export default function CenterLayout({ children }: { children: ReactNode }) {
  // The account pages have no dock of their own: the pages of the center are the User pane of the home page.
  return (
    <AppFrame name="socialnetwork" app="center" css="app-center antialiased" api={null}>
      <OneTimeNotices />
      {children}
    </AppFrame>
  );
}
