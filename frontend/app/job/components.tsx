"use client";

import Link from "next/link";
import { ReactNode } from "react";

import type { User } from "@sn/api";
import AuthGate from "@sn/compounds/AuthGate";
import { JobDescriptionSummary, EMPLOYMENT_LABELS, LanguageItem, Match, Resume, SkillItem, Step, formatDate, formatSalary, label } from "./lib";
import { tr } from "./i18n";
import Card from "@sn/elements/Card";

/** Page frame: the sign-in check, the links of the jobs app and the title; `children(user)` for a signed-in person. */
export function Protected({ title, children }: { title: string; children: (user: User) => ReactNode }) {
  return (
    <AuthGate title={title} heading>
      {children}
    </AuthGate>
  );
}

export function Status({
  loading,
  error,
  empty,
  emptyText,
}: {
  loading: boolean;
  error: string | null;
  empty: boolean;
  emptyText: string;
}) {
  if (loading) return <p className="muted" role="status">{tr("loading")}</p>;
  if (error) return <p role="alert" className="error">{error}</p>;
  if (empty) return <p className="muted">{emptyText}</p>;
  return null;
}

export function JobTile({ job, children }: { job: JobDescriptionSummary; children?: ReactNode }) {
  const salary = formatSalary(job);
  const facts = [
    job.company,
    job.location || null,
    job.remote ? tr("remote") : null,
    EMPLOYMENT_LABELS[job.employment_type],
    salary,
  ].filter((fact): fact is string => Boolean(fact));
  return (
    <Card stack as="article" style={{ height: "100%", boxSizing: "border-box" }}>
      <h2>
        <Link href={`/job/job/${job.id}`}>{job.title}</Link>
      </h2>
      <p className="muted break" style={{ margin: 0 }}>
        {facts.join(" · ")}
      </p>
      {job.snippet && <p className="break" style={{ margin: 0 }}>{job.snippet}</p>}
      {job.tags.length > 0 && (
        <ul className="tags" aria-label={tr("tags")}>
          {job.tags.map((tag) => (
            <li key={tag} className="tag">{tag}</li>
          ))}
        </ul>
      )}
      <p className="muted" style={{ margin: 0 }}>
        {tr("posted")} {formatDate(job.created_at)} {tr("by")} {job.owner_username}
        {job.status === "closed" ? tr("closed") : job.status !== "open" ? ` · ${label(job.status)}` : null}
        {job.expired && tr("expired")}
        {job.applied && tr("applied")}
        {job.saved && tr("saved_2")}
      </p>
      {children}
    </Card>
  );
}

export function Field({
  label,
  grow,
  children,
}: {
  label: string;
  grow?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={grow ? "field grow" : "field"}>
      <span>{label}</span>
      {children}
    </label>
  );
}

/** A skill as a tag: `Python · advanced · 4 yrs`. */
export function SkillTags({ skills, title }: { skills: readonly SkillItem[]; title: string }) {
  if (skills.length === 0) return null;
  return (
    <ul className="tags" aria-label={title}>
      {skills.map((skill, index) => (
        <li key={`${skill.name}-${index}`} className="tag">
          {[skill.name, skill.level ? label(skill.level) : null, skill.years !== null ? `${skill.years} ${tr("years_short")}` : null].filter(Boolean).join(" · ")}
        </li>
      ))}
    </ul>
  );
}

export function LanguageTags({ languages, title }: { languages: readonly LanguageItem[]; title: string }) {
  if (languages.length === 0) return null;
  return (
    <ul className="tags" aria-label={title}>
      {languages.map((item, index) => (
        <li key={`${item.language}-${index}`} className="tag">{item.language} · {label(item.proficiency)}</li>
      ))}
    </ul>
  );
}

function period(start: string | null, end: string | null): string {
  if (!start && !end) return "";
  return `${start ?? ""} – ${end ?? tr("present")}`;
}

/** The resume that came with an application, as text only. */
export function ResumeView({ resume }: { resume: Resume }) {
  return (
    <div className="stack">
      {resume.headline && <p className="break" style={{ margin: 0 }}><strong>{resume.headline}</strong></p>}
      {resume.summary && <p className="prose">{resume.summary}</p>}
      <SkillTags skills={resume.skills} title={tr("skills")} />
      <LanguageTags languages={resume.languages} title={tr("languages")} />
      {resume.experience.length > 0 && (
        <section aria-label={tr("experience")}>
          <h4 style={{ margin: 0 }}>{tr("experience")}</h4>
          <ul className="plain">
            {resume.experience.map((item, index) => (
              <li key={index} className="break">
                <strong>{item.title}</strong> · {item.company} <span className="muted">{period(item.start, item.end)}</span>
                {item.description && <p className="prose" style={{ margin: 0 }}>{item.description}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {resume.education.length > 0 && (
        <section aria-label={tr("education")}>
          <h4 style={{ margin: 0 }}>{tr("education")}</h4>
          <ul className="plain">
            {resume.education.map((item, index) => (
              <li key={index} className="break">
                <strong>{item.school}</strong> · {[item.degree, item.field].filter(Boolean).join(", ")} <span className="muted">{period(item.start, item.end)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/** Each step of an application, with the day and who made it. */
export function StepList({ steps }: { steps: readonly Step[] }) {
  if (steps.length === 0) return null;
  return (
    <ol className="steps" aria-label={tr("history")}>
      {steps.map((step, index) => (
        <li key={index}>
          <strong>{label(step.status)}</strong>{" "}
          <span className="muted">{formatDate(step.at)} · {step.by === "applicant" ? tr("by_applicant") : tr("by_employer")}</span>
        </li>
      ))}
    </ol>
  );
}

/** How well the skills fit: the score, what is there, what is only half there and what is missing. */
export function MatchView({ match }: { match: Match }) {
  if (match.score === null) return null;
  const skills = (names: string[], title: string, mark: string) =>
    names.length > 0 && (
      <p style={{ margin: 0 }} className="break">
        <strong>{mark} {title}:</strong>{" "}
        {names.map((name, index) => (
          <span key={name}>
            {index > 0 && ", "}
            {name}
          </span>
        ))}
      </p>
    );
  return (
    <section className="stack" aria-label={tr("match")}>
      <p style={{ margin: 0 }}><strong>{tr("match")}: {match.score}%</strong></p>
      <progress value={match.score} max={100} aria-label={tr("match")} style={{ width: "100%" }} />
      {skills(match.matched, tr("match_has"), "✓")}
      {skills(match.partial, tr("match_partial"), "~")}
      {skills(match.missing, tr("match_missing"), "✗")}
      {skills(match.missing_preferred, tr("match_missing_preferred"), "✗")}
    </section>
  );
}
