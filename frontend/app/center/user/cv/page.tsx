"use client";

import { Suspense } from "react";

import CvView from "../../components/CvView";

/** The CV page: `/user/cv` (your own, with import) or `/user/cv?u=<name>` (someone's). */
export default function CvPage() {
  return (
    <Suspense fallback={null}>
      <CvView />
    </Suspense>
  );
}
