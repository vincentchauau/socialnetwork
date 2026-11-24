"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { Field, Protected, Status } from "../../components";
import { API, Applicant, JOB_STATUSES, JobDescriptionDetail, JobStatus, errorText, label } from "../../lib";
import { JobDescriptionForm, JobDescriptionPayload } from "../../job-description-form";
import { ApplicantCard } from "./applicant-card";
import Button from "@sn/elements/Button";
import Select from "@sn/elements/Select";
import { tr } from "../../i18n";
import { confirmDialog } from "@sn/compounds/Dialogs";

function Manage({ id }: { id: string }) {
  const router = useRouter();
  const jobPath = `${API}/jobs/${encodeURIComponent(id)}`;
  const [job, setJob] = useState<JobDescriptionDetail | null>(null);
  const [applicants, setApplicants] = useState<Applicant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      apiFetch<JobDescriptionDetail>(jobPath),
      apiFetch<Applicant[]>(`${jobPath}/applications`),
    ])
      .then(([posting, people]) => {
        if (cancelled) return;
        setJob(posting);
        setApplicants(people);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(errorText(e, tr("could_not_load_this_posting")));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobPath]);

  async function patch(body: Partial<JobDescriptionPayload> | { status: string }) {
    const updated = await apiFetch<JobDescriptionDetail>(jobPath, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    setJob(updated);
  }

  async function changeStatus(next: JobStatus) {
    setActionError(null);
    try {
      await patch({ status: next });
    } catch (e) {
      setActionError(errorText(e, tr("could_not_change_the_status")));
    }
  }

  async function remove() {
    if (!(await confirmDialog(tr("delete_this_posting_and_all_of")))) return;
    setActionError(null);
    try {
      await apiFetch(jobPath, { method: "DELETE" });
      router.push("/job/employer");
    } catch (e) {
      setActionError(errorText(e, tr("could_not_delete_the_posting")));
    }
  }

  async function saveEdits(payload: JobDescriptionPayload) {
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
        <Link href="/job/employer">{tr("my_postings_2")}</Link>
      </>
    );
  }

  return (
    <>
      <Link href="/job/employer">{tr("my_postings_2")}</Link>
      <section className="stack card" aria-label={tr("posting")}>
        <h2 className="break">{job.title}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {job.company} · {label(job.status)}
          {job.expired && tr("expired")} · <Link href={`/job/job/${job.id}`}>{tr("view_public_page")}</Link>
        </p>
        <div className="row wrap">
          <Button variant="secondary" className="secondary" onClick={() => setEditing((value) => !value)} aria-expanded={editing}>
            {editing ? tr("cancel_editing") : tr("edit")}
          </Button>
          <Field label={tr("job_status")}>
            <Select value={job.status} onChange={(e) => void changeStatus(e.target.value as JobStatus)}>
              {JOB_STATUSES.map((value) => (
                <option key={value} value={value}>{label(value)}</option>
              ))}
            </Select>
          </Field>
          <Button variant="danger" className="danger" onClick={remove}>{tr("delete")}</Button>
        </div>
        {actionError && <p role="alert" className="error">{actionError}</p>}
      </section>

      {editing && <JobDescriptionForm initial={job} submitLabel={tr("save_changes")} onSubmit={saveEdits} />}

      <h2 style={{ margin: 0 }}>Applicants ({applicants.length})</h2>
      {applicants.length === 0 ? (
        <p className="muted">{tr("nobody_has_applied_yet")}</p>
      ) : (
        <ul className="list" aria-label={tr("applicants")}>
          {applicants.map((applicant) => (
            <ApplicantCard key={applicant.id} applicant={applicant} onChange={replaceApplicant} />
          ))}
        </ul>
      )}
    </>
  );
}

export default function ManageJobDescriptionPage() {
  const params = useParams<{ id: string }>();
  return <Protected title={tr("manage_posting")}>{() => <Manage id={params.id} />}</Protected>;
}
