"use client";

import { useState } from "react";

import { apiFetch } from "@sn/api";
import { Field } from "../../components";
import {
  API,
  APPLICATION_STATUSES,
  Applicant,
  ApplicationStatus,
  LIMITS,
  errorText,
  formatDate,
  label,
} from "../../lib";

/** Mirrors the backend transition map; hired and rejected are terminal. */
const NEXT_STATUSES: Record<ApplicationStatus, ApplicationStatus[]> = {
  submitted: ["reviewing", "shortlisted", "rejected"],
  reviewing: ["shortlisted", "rejected", "hired"],
  shortlisted: ["hired", "rejected"],
  hired: [],
  rejected: [],
};

/** One applicant: their text (rendered as text only), a status selector and a private note. */
export function ApplicantCard({
  applicant,
  onChange,
}: {
  applicant: Applicant;
  onChange: (updated: Applicant) => void;
}) {
  const [status, setStatus] = useState<ApplicationStatus>(applicant.status);
  const [note, setNote] = useState(applicant.note);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const { profile } = applicant;
  const id = `applicant-${applicant.id}`;

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await apiFetch<Applicant>(`${API}/applications/${applicant.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status, note }),
      });
      onChange(updated);
      setSaved(true);
    } catch (e) {
      setError(errorText(e, "Could not update this application"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="card stack" aria-labelledby={id}>
      <h3 id={id} className="break">
        {applicant.applicant_username}
      </h3>
      <p className="muted break" style={{ margin: 0 }}>
        Applied {formatDate(applicant.created_at)}
        {applicant.contact_email && ` · ${applicant.contact_email}`}
      </p>
      {profile && (
        <div className="stack">
          {profile.headline && <p className="break" style={{ margin: 0 }}><strong>{profile.headline}</strong></p>}
          {profile.open_to_work && <p className="muted" style={{ margin: 0 }}>Open to work</p>}
          {profile.skills.length > 0 && (
            <ul className="tags" aria-label="Skills">
              {profile.skills.map((skill) => (
                <li key={skill} className="tag">{skill}</li>
              ))}
            </ul>
          )}
          {profile.about && <p className="prose">{profile.about}</p>}
        </div>
      )}
      {applicant.cover_letter && (
        <details>
          <summary>Cover letter</summary>
          <p className="prose">{applicant.cover_letter}</p>
        </details>
      )}
      {applicant.resume_text && (
        <details>
          <summary>Resume</summary>
          <p className="prose">{applicant.resume_text}</p>
        </details>
      )}
      <div className="row wrap">
        <Field label="Status" grow>
          <select value={status} onChange={(e) => setStatus(e.target.value as ApplicationStatus)}>
            {APPLICATION_STATUSES.filter(
              (value) => value === applicant.status || NEXT_STATUSES[applicant.status].includes(value),
            ).map((value) => (
              <option key={value} value={value}>{label(value)}</option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="Private note (only you can see this)">
        <textarea rows={3} maxLength={LIMITS.note} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      {error && <p role="alert" className="error">{error}</p>}
      {saved && <p role="status" className="ok">Saved.</p>}
      <div className="row">
        <button onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      </div>
    </li>
  );
}
