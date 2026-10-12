"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { Field, Protected, Status } from "../../components";
import {
  API,
  EMPLOYMENT_LABELS,
  LIMITS,
  PostingDetail,
  errorText,
  formatDate,
  formatSalary,
} from "../../lib";

function ApplyForm({ jobId, onApplied }: { jobId: number; onApplied: () => void }) {
  const [coverLetter, setCoverLetter] = useState("");
  const [resume, setResume] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`${API}/jobs/${jobId}/apply`, {
        method: "POST",
        body: JSON.stringify({
          cover_letter: coverLetter,
          resume_text: resume,
          contact_email: email.trim() || null,
        }),
      });
      onApplied();
    } catch (e) {
      setError(errorText(e, "Could not submit your application"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack card" onSubmit={submit} aria-label="Apply">
      <h2>Apply</h2>
      <Field label="Cover letter">
        <textarea
          rows={6}
          maxLength={LIMITS.coverLetter}
          value={coverLetter}
          onChange={(e) => setCoverLetter(e.target.value)}
        />
      </Field>
      <Field label="Resume (plain text)">
        <textarea
          rows={8}
          maxLength={LIMITS.resume}
          value={resume}
          onChange={(e) => setResume(e.target.value)}
        />
      </Field>
      <Field label="Contact email (optional)">
        <input
          type="email"
          maxLength={LIMITS.email}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </Field>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="row">
        <button disabled={busy}>{busy ? "Sending…" : "Submit application"}</button>
      </div>
    </form>
  );
}

function JobView({ id }: { id: string }) {
  const [job, setJob] = useState<PostingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiFetch<PostingDetail>(`${API}/jobs/${encodeURIComponent(id)}`)
      .then((data) => {
        if (!cancelled) setJob(data);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(errorText(e, "Could not load this job"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function toggleSave(current: PostingDetail) {
    setSaving(true);
    setActionError(null);
    try {
      await apiFetch(`${API}/jobs/${current.id}/save`, {
        method: current.saved ? "DELETE" : "PUT",
      });
      setJob({ ...current, saved: !current.saved });
    } catch (e) {
      setActionError(errorText(e, "Could not update saved jobs"));
    } finally {
      setSaving(false);
    }
  }

  if (loading || error || !job) {
    return (
      <>
        <Status loading={loading} error={error} empty={false} emptyText="" />
        <Link href="/">← All jobs</Link>
      </>
    );
  }

  const salary = formatSalary(job);
  const canApply = !job.is_owner && !job.applied && job.status === "open" && !job.expired;

  return (
    <>
      <Link href="/">← All jobs</Link>
      <article className="stack card">
        <h2 className="break">{job.title}</h2>
        <p className="muted break" style={{ margin: 0 }}>
          {[job.company, job.location || null, job.remote ? "Remote" : null]
            .filter(Boolean)
            .join(" · ")}
        </p>
        <p style={{ margin: 0 }}>
          {EMPLOYMENT_LABELS[job.employment_type]}
          {salary && ` · ${salary}`}
        </p>
        {job.tags.length > 0 && (
          <ul className="tags" aria-label="Tags">
            {job.tags.map((tag) => (
              <li key={tag} className="tag">{tag}</li>
            ))}
          </ul>
        )}
        <p className="muted" style={{ margin: 0 }}>
          Posted {formatDate(job.created_at)} by {job.owner_username}
          {job.expires_at && ` · ${job.expired ? "Expired" : "Expires"} ${formatDate(job.expires_at)}`}
          {job.status === "closed" && " · Closed"}
        </p>
        {/* Plain text only: React escapes it, CSS keeps the line breaks. */}
        <p className="prose">{job.description || "No description provided."}</p>
        <div className="row wrap">
          {job.is_owner ? (
            <Link href={`/employer/${job.id}`}>Manage posting ({job.application_count ?? 0} applicants)</Link>
          ) : (
            <button
              className="secondary"
              onClick={() => toggleSave(job)}
              disabled={saving}
              aria-pressed={job.saved}
            >
              {job.saved ? "Saved ✓" : "Save job"}
            </button>
          )}
        </div>
        {actionError && <p role="alert" className="error">{actionError}</p>}
      </article>

      {job.applied && (
        <p className="ok" role="status">
          You applied to this job. <Link href="/applications">View your applications</Link>
        </p>
      )}
      {!job.is_owner && !job.applied && !canApply && (
        <p className="muted">This posting is no longer accepting applications.</p>
      )}
      {canApply && (
        <ApplyForm jobId={job.id} onApplied={() => setJob({ ...job, applied: true })} />
      )}
    </>
  );
}

export default function JobPage() {
  const params = useParams<{ id: string }>();
  return <Protected title="Job">{() => <JobView id={params.id} />}</Protected>;
}
