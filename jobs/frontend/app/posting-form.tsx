"use client";

import { FormEvent, useState } from "react";

import { Field } from "./components";
import {
  EMPLOYMENT_LABELS,
  EmploymentType,
  LIMITS,
  PostingDetail,
  errorText,
  parseTags,
} from "./lib";

export interface PostingPayload {
  title: string;
  company: string;
  location: string;
  remote: boolean;
  employment_type: EmploymentType;
  salary_min: number | null;
  salary_max: number | null;
  currency: string;
  description: string;
  tags: string[];
  expires_at: string | null;
}

function toNumber(raw: string): number | null {
  const trimmed = raw.trim();
  return trimmed === "" ? null : Number(trimmed);
}

/** The date-only value of an ISO timestamp, for <input type="date">. */
function dateValue(iso: string | null): string {
  return iso ? iso.slice(0, 10) : "";
}

export function PostingForm({
  initial,
  submitLabel,
  onSubmit,
}: {
  initial?: PostingDetail;
  submitLabel: string;
  onSubmit: (payload: PostingPayload) => Promise<void>;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [company, setCompany] = useState(initial?.company ?? "");
  const [location, setLocation] = useState(initial?.location ?? "");
  const [remote, setRemote] = useState(initial?.remote ?? false);
  const [type, setType] = useState<EmploymentType>(initial?.employment_type ?? "full_time");
  const [salaryMin, setSalaryMin] = useState(initial?.salary_min?.toString() ?? "");
  const [salaryMax, setSalaryMax] = useState(initial?.salary_max?.toString() ?? "");
  const [currency, setCurrency] = useState(initial?.currency ?? "USD");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [tags, setTags] = useState(initial?.tags.join(", ") ?? "");
  const [expires, setExpires] = useState(dateValue(initial?.expires_at ?? null));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const min = toNumber(salaryMin);
    const max = toNumber(salaryMax);
    if (min !== null && max !== null && min > max) {
      setError("Minimum salary cannot exceed maximum salary");
      return;
    }
    const tagList = parseTags(tags);
    if (tagList.length > LIMITS.tags) {
      setError(`Use at most ${LIMITS.tags} tags`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        title: title.trim(),
        company: company.trim(),
        location: location.trim(),
        remote,
        employment_type: type,
        salary_min: min,
        salary_max: max,
        currency: currency.trim().toUpperCase(),
        description,
        tags: tagList,
        expires_at: expires ? `${expires}T23:59:59Z` : null,
      });
    } catch (e) {
      setError(errorText(e, "Could not save the posting"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack card" onSubmit={submit}>
      <Field label="Title">
        <input required maxLength={LIMITS.title} value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field label="Company">
        <input required maxLength={LIMITS.company} value={company} onChange={(e) => setCompany(e.target.value)} />
      </Field>
      <div className="row wrap">
        <Field label="Location" grow>
          <input maxLength={LIMITS.location} value={location} onChange={(e) => setLocation(e.target.value)} />
        </Field>
        <Field label="Employment type" grow>
          <select value={type} onChange={(e) => setType(e.target.value as EmploymentType)}>
            {Object.entries(EMPLOYMENT_LABELS).map(([value, text]) => (
              <option key={value} value={value}>{text}</option>
            ))}
          </select>
        </Field>
      </div>
      <label className="row wrap">
        <input type="checkbox" checked={remote} onChange={(e) => setRemote(e.target.checked)} />
        <span>Remote</span>
      </label>
      <div className="row wrap">
        <Field label="Minimum salary" grow>
          <input type="number" min={0} inputMode="numeric" value={salaryMin} onChange={(e) => setSalaryMin(e.target.value)} />
        </Field>
        <Field label="Maximum salary" grow>
          <input type="number" min={0} inputMode="numeric" value={salaryMax} onChange={(e) => setSalaryMax(e.target.value)} />
        </Field>
        <Field label="Currency (3 letters)" grow>
          <input required minLength={3} maxLength={3} pattern="[A-Za-z]{3}" value={currency} onChange={(e) => setCurrency(e.target.value)} />
        </Field>
      </div>
      <Field label="Description (plain text)">
        <textarea rows={10} maxLength={LIMITS.description} value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <Field label={`Tags (comma separated, up to ${LIMITS.tags})`}>
        <input value={tags} onChange={(e) => setTags(e.target.value)} />
      </Field>
      <Field label="Expires on (optional)">
        <input type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
      </Field>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="row">
        <button disabled={busy}>{busy ? "Saving…" : submitLabel}</button>
      </div>
    </form>
  );
}
