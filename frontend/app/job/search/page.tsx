"use client";

import JobSearch from "../JobSearch";
import { Protected } from "../components";
import { tr } from "../i18n";

export default function SearchPage() {
  return <Protected title={tr("jobs")}>{() => <JobSearch />}</Protected>;
}
