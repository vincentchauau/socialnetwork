import type { Metadata } from "next";
import type { ReactNode } from "react";
import AppFrame from "../chat/dock/AppFrame";
import "./jobs.css";

export const metadata: Metadata = { title: "Jobs · Social Network" };

export default function JobsLayout({ children }: { children: ReactNode }) {
  return (
    <AppFrame name="Jobs" app="jobs" css="app-jobs" except={["/job/job/"]}>{children}</AppFrame>
  );
}
