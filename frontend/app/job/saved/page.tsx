"use client";

import { Protected } from "../components";
import SavedList from "../SavedList";
import { tr } from "../i18n";

export default function SavedPage() {
  return <Protected title={tr("saved_jobs")}>{() => <SavedList />}</Protected>;
}
