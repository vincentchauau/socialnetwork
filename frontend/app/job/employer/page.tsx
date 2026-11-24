"use client";

import { Protected } from "../components";
import MyPostings from "../MyPostings";
import { tr } from "../i18n";

export default function EmployerPage() {
  return <Protected title={tr("employer")}>{() => <MyPostings />}</Protected>;
}
