"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import Alert from "@sn/elements/Alert";
import { ApplicantCard } from "./employer/[id]/applicant-card";
import { API, Applicant, JobDescriptionSummary, errorText } from "./lib";
import { tr } from "./i18n";

/** The applicants of every job the person posts, in one list: the employer approves them step by step (the same steps as on the job's page). */
export default function ApproveList() {
  const [applicants, setApplicants] = useState<Applicant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const jobs = await apiFetch<JobDescriptionSummary[]>(`${API}/me/jobs`);
        const lists = await Promise.all(jobs.map((job) => apiFetch<Applicant[]>(`${API}/jobs/${job.id}/applications`)));
        if (alive) setApplicants(lists.flat());
      } catch (failure) {
        if (alive) setError(errorText(failure));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const replaceApplicant = (updated: Applicant) =>
    setApplicants((current) => current.map((applicant) => (applicant.id === updated.id ? updated : applicant)));

  if (loading) return <p role="status" className="muted">{tr("loading")}</p>;
  if (error) return <Alert tone="error">{error}</Alert>;
  if (applicants.length === 0) return <p className="muted">{tr("no_applicants_to_approve")}</p>;
  return (
    <ul className="list" aria-label={tr("approve_applicants")}>
      {applicants.map((applicant) => (
        <ApplicantCard key={applicant.id} applicant={applicant} onChange={replaceApplicant} />
      ))}
    </ul>
  );
}
