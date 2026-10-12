"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { JobCard, Protected, Status } from "../components";
import { API, PostingSummary, errorText } from "../lib";

function SavedList() {
  const [items, setItems] = useState<PostingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<PostingSummary[]>(`${API}/me/saved`)
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(errorText(e, "Could not load saved jobs"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function remove(id: number) {
    setError(null);
    try {
      await apiFetch(`${API}/jobs/${id}/save`, { method: "DELETE" });
      setItems((current) => current.filter((job) => job.id !== id));
    } catch (e) {
      setError(errorText(e, "Could not remove this job"));
    }
  }

  return (
    <>
      <Status loading={loading} error={error} empty={items.length === 0} emptyText="You have no saved jobs yet." />
      {!loading && items.length > 0 && (
        <ul className="list" aria-label="Saved jobs">
          {items.map((job) => (
            <JobCard key={job.id} job={job}>
              <div className="row">
                <button className="secondary" onClick={() => remove(job.id)}>
                  Remove from saved
                </button>
              </div>
            </JobCard>
          ))}
        </ul>
      )}
    </>
  );
}

export default function SavedPage() {
  return <Protected title="Saved jobs">{() => <SavedList />}</Protected>;
}
