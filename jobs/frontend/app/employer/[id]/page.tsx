"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { Protected, Status } from "../../components";
import { API, Applicant, PostingDetail, errorText, label } from "../../lib";
import { PostingForm, PostingPayload } from "../../posting-form";
import { ApplicantCard } from "./applicant-card";

function Manage({ id }: { id: string }) {
  const router = useRouter();
  const jobPath = `${API}/jobs/${encodeURIComponent(id)}`;
  const [job, setJob] = useState<PostingDetail | null>(null);
  const [applicants, setApplicants] = useState<Applicant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      apiFetch<PostingDetail>(jobPath),
      apiFetch<Applicant[]>(`${jobPath}/applications`),
    ])
      .then(([posting, people]) => {
        if (cancelled) return;
        setJob(posting);
        setApplicants(people);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(errorText(e, "Could not load this posting"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobPath]);

  async function patch(body: Partial<PostingPayload> | { status: string }) {
    const updated = await apiFetch<PostingDetail>(jobPath, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    setJob(updated);
  }

  async function toggleStatus(current: PostingDetail) {
    setActionError(null);
    try {
      await patch({ status: current.status === "open" ? "closed" : "open" });
    } catch (e) {
      setActionError(errorText(e, "Could not change the status"));
    }
  }

  async function remove() {
    if (!window.confirm("Delete this posting and all of its applications?")) return;
    setActionError(null);
    try {
      await apiFetch(jobPath, { method: "DELETE" });
      router.push("/employer");
    } catch (e) {
      setActionError(errorText(e, "Could not delete the posting"));
    }
  }

  async function saveEdits(payload: PostingPayload) {
    await patch(payload);
    setEditing(false);
  }

  function replaceApplicant(updated: Applicant) {
    setApplicants((current) => current.map((a) => (a.id === updated.id ? updated : a)));
  }

  if (loading || error || !job) {
    return (
      <>
        <Status loading={loading} error={error} empty={false} emptyText="" />
        <Link href="/employer">← My postings</Link>
      </>
    );
  }

  return (
    <>
      <Link href="/employer">← My postings</Link>
      <section className="stack card" aria-label="Posting">
        <h2 className="break">{job.title}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {job.company} · {label(job.status)}
          {job.expired && " · Expired"} · <Link href={`/job/${job.id}`}>View public page</Link>
        </p>
        <div className="row wrap">
          <button className="secondary" onClick={() => setEditing((value) => !value)} aria-expanded={editing}>
            {editing ? "Cancel editing" : "Edit"}
          </button>
          <button className="secondary" onClick={() => toggleStatus(job)}>
            {job.status === "open" ? "Close posting" : "Reopen posting"}
          </button>
          <button className="danger" onClick={remove}>Delete</button>
        </div>
        {actionError && <p role="alert" className="error">{actionError}</p>}
      </section>

      {editing && <PostingForm initial={job} submitLabel="Save changes" onSubmit={saveEdits} />}

      <h2 style={{ margin: 0 }}>Applicants ({applicants.length})</h2>
      {applicants.length === 0 ? (
        <p className="muted">Nobody has applied yet.</p>
      ) : (
        <ul className="list" aria-label="Applicants">
          {applicants.map((applicant) => (
            <ApplicantCard key={applicant.id} applicant={applicant} onChange={replaceApplicant} />
          ))}
        </ul>
      )}
    </>
  );
}

export default function ManagePostingPage() {
  const params = useParams<{ id: string }>();
  return <Protected title="Manage posting">{() => <Manage id={params.id} />}</Protected>;
}
