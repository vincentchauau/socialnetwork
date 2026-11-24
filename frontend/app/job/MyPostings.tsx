"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { GridView } from "@sn/compounds/GalleryView";
import { JobTile, Status } from "./components";
import { API, JobDescriptionSummary, errorText } from "./lib";
import { tr } from "./i18n";

export default function MyPostings() {
  const [items, setItems] = useState<JobDescriptionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<JobDescriptionSummary[]>(`${API}/me/jobs`)
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(errorText(e, tr("could_not_load_your_postings")));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <div className="row">
        <Link href="/job/employer/new">{tr("post_a_job")}</Link>
      </div>
      <Status loading={loading} error={error} empty={items.length === 0} emptyText={tr("you_have_not_posted_any_jobs")} />
      {!loading && items.length > 0 && (
        <GridView
          items={items}
          itemKey={(job) => job.id}
          label={tr("my_postings")}
          minColumnWidth={320}
          gap={12}
          renderItem={(job) => (
            <JobTile job={job}>
              <p style={{ margin: 0 }}>
                <strong>{job.application_count ?? 0}</strong> {tr("applicant")}
                {job.application_count === 1 ? "" : "s"} ·{" "}
                <Link href={`/job/employer/${job.id}`}>{tr("manage")}</Link>
              </p>
            </JobTile>
          )}
        />
      )}
    </>
  );
}
