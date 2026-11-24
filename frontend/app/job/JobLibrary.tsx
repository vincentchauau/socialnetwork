"use client";

import { useState } from "react";

import { TabPanel } from "@sn/compounds/SplitPanel";

import ApplicationsList from "./applications/ApplicationsList";
import ApproveList from "./ApproveList";
import JobSearch from "./JobSearch";
import MyPostings from "./MyPostings";
import PendingApplications from "./PendingApplications";
import SavedList from "./SavedList";
import { tr } from "./i18n";
import "./jobs.css";

/** The jobs the way a job site shows them: search first, then the jobs saved, the applications, and what the person posts as an employer. No props, no page chrome. */
export default function JobLibrary() {
  // The page opens on the search (the first tab of the job site is the employer's, in the order of the market).
  const [tab, setTab] = useState("search");
  return (
    <TabPanel
      aria-label={tr("jobs")}
      keepMounted={false}
      activeKey={tab}
      onChange={setTab}
      data={[
        { key: "postings", label: tr("tab_crud_descriptions") },
        { key: "saved", label: tr("tab_saved_descriptions") },
        { key: "search", label: tr("tab_create_application") },
        { key: "update", label: tr("tab_update_application") },
        { key: "approve", label: tr("tab_approve_application") },
        { key: "applications", label: tr("tab_my_applications") },
      ]}
      panels={{ postings: <MyPostings />, search: <JobSearch />, update: <PendingApplications />, approve: <ApproveList />, applications: <ApplicationsList />, saved: <SavedList /> }}
    />
  );
}
