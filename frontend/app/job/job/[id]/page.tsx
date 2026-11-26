"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { apiFetch, type User } from "@sn/api";
import Comments from "@sn/compounds/Comments";
import { Field, LanguageTags, MatchView, Protected, SkillTags, Status } from "../../components";
import {
  API,
  EMPLOYMENT_LABELS,
  LIMITS,
  JobDescriptionDetail,
  PROFILE_API,
  Resume,
  errorText,
  formatDate,
  formatSalary,
  hasResume,
  label,
  resumeFromProfile,
} from "../../lib";
import CheckBox from "@sn/elements/CheckBox";
import Button from "@sn/elements/Button";
import { tr } from "../../i18n";
import TextBox from "@sn/elements/TextBox";

function ApplyForm({ jobId, onApplied }: { jobId: number; onApplied: () => void }) {
  const [coverLetter, setCoverLetter] = useState("");
  const [email, setEmail] = useState("");
  const [profile, setProfile] = useState<Resume | null | undefined>(undefined); // undefined: not read yet
  const [withProfile, setWithProfile] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The resume of an application is the profile of the account: read here, sent with the application, kept as it was.
  useEffect(() => {
    let cancelled = false;
    apiFetch<Record<string, unknown>>(PROFILE_API)
      .then((data) => {
        if (!cancelled) setProfile(resumeFromProfile(data));
      })
      .catch(() => {
        if (!cancelled) setProfile(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const profileToSend = profile && hasResume(profile) ? profile : null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`${API}/jobs/${jobId}/apply`, {
        method: "POST",
        body: JSON.stringify({
          cover_letter: coverLetter,
          resume: withProfile ? profileToSend : null,
          contact_email: email.trim() || null,
        }),
      });
      onApplied();
    } catch (e) {
      setError(errorText(e, tr("could_not_submit_your_application")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack card" onSubmit={submit} aria-label={tr("apply")}>
      <h2>{tr("apply")}</h2>
      <Field label={tr("cover_letter")}>
        <TextBox multiline
          rows={6}
          maxLength={LIMITS.coverLetter}
          value={coverLetter}
          onChange={(e) => setCoverLetter(e.target.value)}
        />
      </Field>
      {profile !== undefined &&
        (profileToSend ? (
          <CheckBox checked={withProfile} onChange={setWithProfile} label={tr("include_my_profile")} />
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            {tr("profile_is_empty")} <Link href="/user">{tr("edit_profile")}</Link>
          </p>
        ))}
      <Field label={tr("contact_email_optional")}>
        <TextBox
          type="email"
          maxLength={LIMITS.email}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </Field>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="row">
        <Button disabled={busy}>{busy ? tr("sending") : tr("submit_application")}</Button>
      </div>
    </form>
  );
}

/** What the job asks of a person: the experience and education, then the skills and the languages. */
function JobRequirements({ job }: { job: JobDescriptionDetail }) {
  const facts = [
    job.experience_min_years !== null ? tr("p0_years_of_experience", { p0: job.experience_min_years }) : null,
    job.education_min ? `${tr("education_min")}: ${job.education_min === "none" ? tr("edu_none") : tr(job.education_min)}` : null,
  ].filter(Boolean);
  if (facts.length === 0 && job.skills_required.length + job.skills_preferred.length + job.languages.length === 0) return null;
  return (
    <section className="stack" aria-label={tr("requirements")}>
      <h3 style={{ margin: 0 }}>{tr("requirements")}</h3>
      {facts.length > 0 && <p style={{ margin: 0 }}>{facts.join(" · ")}</p>}
      <SkillTags skills={job.skills_required} title={tr("required_skills")} />
      <SkillTags skills={job.skills_preferred} title={tr("preferred_skills")} />
      <LanguageTags languages={job.languages} title={tr("languages")} />
      {job.match && <MatchView match={job.match} />}
    </section>
  );
}

function JobPoints({ title, lines }: { title: string; lines: readonly string[] }) {
  if (lines.length === 0) return null;
  return (
    <section aria-label={title}>
      <h3 style={{ margin: 0 }}>{title}</h3>
      <ul className="points">
        {lines.map((line, index) => (
          <li key={index} className="break">{line}</li>
        ))}
      </ul>
    </section>
  );
}

function JobView({ id, user }: { id: string; user: User }) {
  const [job, setJob] = useState<JobDescriptionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiFetch<JobDescriptionDetail>(`${API}/jobs/${encodeURIComponent(id)}`)
      .then((data) => {
        if (!cancelled) setJob(data);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(errorText(e, tr("could_not_load_this_job")));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);


  if (loading || error || !job) {
    return (
      <>
        <Status loading={loading} error={error} empty={false} emptyText="" />
      </>
    );
  }

  const salary = formatSalary(job);
  const canApply = !job.is_owner && !job.applied && job.status === "open" && !job.expired;

  return (
    <>
      <article className="stack card">
        <h2 className="break">{job.title}</h2>
        <p className="muted break" style={{ margin: 0 }}>
          {[job.company, job.location || null, job.remote ? tr("remote") : null]
            .filter(Boolean)
            .join(" · ")}
        </p>
        <p style={{ margin: 0 }}>
          {EMPLOYMENT_LABELS[job.employment_type]}
          {job.seniority && ` · ${tr(job.seniority)}`}
          {salary && tr("salary", { salary })}
        </p>
        <p className="muted" style={{ margin: 0 }}>
          {[job.department || null, tr("p0_openings", { p0: job.openings })].filter(Boolean).join(" · ")}
        </p>
        {job.tags.length > 0 && (
          <ul className="tags" aria-label={tr("tags")}>
            {job.tags.map((tag) => (
              <li key={tag} className="tag">{tag}</li>
            ))}
          </ul>
        )}
        <p className="muted" style={{ margin: 0 }}>
          {tr("posted")} {formatDate(job.created_at)} {tr("by")} {job.owner_username}
          {job.expires_at && ` · ${job.expired ? "Expired" : "Expires"} ${formatDate(job.expires_at)}`}
          {job.status === "closed" ? tr("closed") : job.status !== "open" ? ` · ${label(job.status)}` : null}
        </p>
        {/* Plain text only: React escapes it, CSS keeps the line breaks. */}
        <p className="prose">{job.description || tr("no_description_provided")}</p>
        <JobRequirements job={job} />
        <JobPoints title={tr("responsibilities")} lines={job.responsibilities} />
        <JobPoints title={tr("benefits")} lines={job.benefits} />
        <div className="row wrap">
          {job.is_owner ? (
            <Link href={`/job/employer/${job.id}`}>Manage posting ({job.application_count ?? 0} {tr("applicants_2")}</Link>
          ) : null}
        </div>
      </article>

      {job.applied && (
        <p className="ok" role="status">
          {tr("you_applied_to_this_job")} <Link href="/job/applications">{tr("view_your_applications")}</Link>
        </p>
      )}
      {!job.is_owner && !job.applied && !canApply && (
        <p className="muted">{tr("this_posting_is_no_longer_accepting")}</p>
      )}
      {canApply && (
        <ApplyForm jobId={job.id} onApplied={() => setJob({ ...job, applied: true })} />
      )}

      <section className="stack card" aria-labelledby="job-comments">
        <h2 id="job-comments" style={{ margin: 0 }}>{tr("comments")}</h2>
        <Comments
          collection={`${API}/jobs/${job.id}/comments`}
          item={`${API}/comments`}
          me={user.username}
          canModerate={job.is_owner}
          label={tr("comments")}
        />
      </section>
    </>
  );
}

export default function JobPage() {
  const params = useParams<{ id: string }>();
  return <Protected title={tr("job")}>{(user) => <JobView id={params.id} user={user} />}</Protected>;
}
