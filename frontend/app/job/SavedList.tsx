"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { GridView } from "@sn/compounds/GalleryView";
import { JobTile, Status } from "./components";
import { API, JobDescriptionSummary, errorText } from "./lib";
import Button from "@sn/elements/Button";
import { tr } from "./i18n";

export default function SavedList() {
  const [items, setItems] = useState<JobDescriptionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<JobDescriptionSummary[]>(`${API}/me/saved`)
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(errorText(e, tr("could_not_load_saved_jobs")));
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
      setError(errorText(e, tr("could_not_remove_this_job")));
    }
  }

  return (
    <>
      <Status loading={loading} error={error} empty={items.length === 0} emptyText={tr("you_have_no_saved_jobs_yet")} />
      {!loading && items.length > 0 && (
        <GridView
          items={items}
          itemKey={(job) => job.id}
          label={tr("saved_jobs")}
          minColumnWidth={320}
          gap={12}
          renderItem={(job) => (
            <JobTile job={job}>
              <div className="row">
                <Button variant="secondary" className="secondary" onClick={() => remove(job.id)}>
                  Remove from saved
                </Button>
              </div>
            </JobTile>
          )}
        />
      )}
    </>
  );
}
