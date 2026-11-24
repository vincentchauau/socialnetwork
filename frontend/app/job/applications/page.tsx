"use client";

import { Protected } from "../components";
import { tr } from "../i18n";
import ApplicationsList from "./ApplicationsList";

export default function ApplicationsPage() {
  return <Protected title={tr("my_applications")}>{() => <ApplicationsList />}</Protected>;
}
