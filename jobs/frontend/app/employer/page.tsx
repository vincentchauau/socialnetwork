"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { JobCard, Protected, Status } from "../components";
import { API, PostingSummary, errorText } from "../lib";

function MyPostings() {
  const [items, setItems] = useState<PostingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<PostingSummary[]>(`${API}/me/postings`)
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(errorText(e, "Could not load your postings"));
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
        <Link href="/employer/new">Post a job</Link>
      </div>
      <Status loading={loading} error={error} empty={items.length === 0} emptyText="You have not posted any jobs yet." />
      {!loading && items.length > 0 && (
        <ul className="list" aria-label="My postings">
          {items.map((job) => (
            <JobCard key={job.id} job={job}>
              <p style={{ margin: 0 }}>
                <strong>{job.application_count ?? 0}</strong> applicant
                {job.application_count === 1 ? "" : "s"} ·{" "}
                <Link href={`/employer/${job.id}`}>Manage</Link>
              </p>
            </JobCard>
          ))}
        </ul>
      )}
    </>
  );
}

export default function EmployerPage() {
  return <Protected title="Employer">{() => <MyPostings />}</Protected>;
}
