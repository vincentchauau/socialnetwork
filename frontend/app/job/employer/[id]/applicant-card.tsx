"use client";

import { useState } from "react";

import { apiFetch } from "@sn/api";
import { Field, MatchView, ResumeView, StepList } from "../../components";
import {
  API,
  APPLICATION_STATUSES,
  Applicant,
  ApplicationStatus,
  LIMITS,
  NEXT_STATUSES,
  errorText,
  formatDate,
  label,
} from "../../lib";
import Button from "@sn/elements/Button";
import { tr } from "../../i18n";
import Select from "@sn/elements/Select";
import TextBox from "@sn/elements/TextBox";
import Card from "@sn/elements/Card";

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
  const { resume } = applicant;
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
      setError(errorText(e, tr("could_not_update_this_application")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card stack as="li" aria-labelledby={id}>
      <h3 id={id} className="break">
        {applicant.applicant_username}
      </h3>
      <p className="muted break" style={{ margin: 0 }}>
        {tr("applied_3")} {formatDate(applicant.created_at)}
        {applicant.contact_email && ` · ${applicant.contact_email}`}
      </p>
      {applicant.match && <MatchView match={applicant.match} />}
      {resume && <ResumeView resume={resume} />}
      <StepList steps={applicant.history} />
      {applicant.cover_letter && (
        <details>
          <summary>{tr("cover_letter")}</summary>
          <p className="prose">{applicant.cover_letter}</p>
        </details>
      )}
      <div className="row wrap">
        <Field label={tr("status_2")} grow>
          <Select value={status} onChange={(e) => setStatus(e.target.value as ApplicationStatus)}>
            {APPLICATION_STATUSES.filter(
              (value) => value === applicant.status || NEXT_STATUSES[applicant.status].includes(value),
            ).map((value) => (
              <option key={value} value={value}>{label(value)}</option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label={tr("private_note_only_you_can_see")}>
        <TextBox multiline rows={3} maxLength={LIMITS.note} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      {error && <p role="alert" className="error">{error}</p>}
      {saved && <p role="status" className="ok">{tr("saved_3")}</p>}
      <div className="row">
        <Button onClick={save} disabled={busy}>{busy ? tr("saving") : tr("save")}</Button>
      </div>
    </Card>
  );
}
