"use client";

import { FormEvent, useState } from "react";

import { Field } from "./components";
import {
  EDUCATIONS,
  EMPLOYMENT_LABELS,
  EmploymentType,
  Education,
  JobDescriptionDetail,
  LIMITS,
  LanguageItem,
  SALARY_PERIODS,
  SENIORITIES,
  SalaryPeriod,
  Seniority,
  SkillItem,
  errorText,
  languagesToText,
  linesToText,
  parseLanguages,
  parseLines,
  parseSkills,
  parseTags,
  skillsToText,
} from "./lib";
import Button from "@sn/elements/Button";
import { tr } from "./i18n";
import Select from "@sn/elements/Select";
import TextBox from "@sn/elements/TextBox";
import CheckBox from "@sn/elements/CheckBox";

export interface JobDescriptionPayload {
  title: string;
  company: string;
  department: string;
  location: string;
  remote: boolean;
  employment_type: EmploymentType;
  seniority: Seniority | null;
  openings: number;
  experience_min_years: number | null;
  education_min: Education | null;
  skills_required: SkillItem[];
  skills_preferred: SkillItem[];
  languages: LanguageItem[];
  responsibilities: string[];
  benefits: string[];
  salary_min: number | null;
  salary_max: number | null;
  currency: string;
  salary_period: SalaryPeriod | null;
  description: string;
  tags: string[];
  expires_at: string | null;
  /** Only when a job is made: a draft is seen by its owner alone. */
  status?: "draft" | "open";
}

function toNumber(raw: string): number | null {
  const trimmed = raw.trim();
  return trimmed === "" ? null : Number(trimmed);
}

/** The date-only value of an ISO timestamp, for <TextBox type="date">. */
function dateValue(iso: string | null): string {
  return iso ? iso.slice(0, 10) : "";
}

export function JobDescriptionForm({
  initial,
  submitLabel,
  onSubmit,
}: {
  initial?: JobDescriptionDetail;
  submitLabel: string;
  onSubmit: (payload: JobDescriptionPayload) => Promise<void>;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [company, setCompany] = useState(initial?.company ?? "");
  const [department, setDepartment] = useState(initial?.department ?? "");
  const [location, setLocation] = useState(initial?.location ?? "");
  const [remote, setRemote] = useState(initial?.remote ?? false);
  const [type, setType] = useState<EmploymentType>(initial?.employment_type ?? "full_time");
  const [seniority, setSeniority] = useState<Seniority | "">(initial?.seniority ?? "");
  const [openings, setOpenings] = useState(String(initial?.openings ?? 1));
  const [experience, setExperience] = useState(initial?.experience_min_years?.toString() ?? "");
  const [education, setEducation] = useState<Education | "">(initial?.education_min ?? "");
  const [required, setRequired] = useState(skillsToText(initial?.skills_required ?? []));
  const [preferred, setPreferred] = useState(skillsToText(initial?.skills_preferred ?? []));
  const [languages, setLanguages] = useState(languagesToText(initial?.languages ?? []));
  const [responsibilities, setResponsibilities] = useState(linesToText(initial?.responsibilities ?? []));
  const [benefits, setBenefits] = useState(linesToText(initial?.benefits ?? []));
  const [salaryMin, setSalaryMin] = useState(initial?.salary_min?.toString() ?? "");
  const [salaryMax, setSalaryMax] = useState(initial?.salary_max?.toString() ?? "");
  const [currency, setCurrency] = useState(initial?.currency ?? "USD");
  const [period, setPeriod] = useState<SalaryPeriod | "">(initial?.salary_period ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [tags, setTags] = useState(initial?.tags.join(", ") ?? "");
  const [expires, setExpires] = useState(dateValue(initial?.expires_at ?? null));
  const [draft, setDraft] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const min = toNumber(salaryMin);
    const max = toNumber(salaryMax);
    if (min !== null && max !== null && min > max) {
      setError(tr("minimum_salary_cannot_exceed_maximum_salary"));
      return;
    }
    const tagList = parseTags(tags);
    if (tagList.length > LIMITS.tags) {
      setError(tr("use_at_most_p0_tags", { p0: LIMITS.tags }));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        title: title.trim(),
        company: company.trim(),
        department: department.trim(),
        location: location.trim(),
        remote,
        employment_type: type,
        seniority: seniority || null,
        openings: Math.max(1, toNumber(openings) ?? 1),
        experience_min_years: toNumber(experience),
        education_min: education || null,
        skills_required: parseSkills(required),
        skills_preferred: parseSkills(preferred),
        languages: parseLanguages(languages),
        responsibilities: parseLines(responsibilities),
        benefits: parseLines(benefits),
        salary_min: min,
        salary_max: max,
        currency: currency.trim().toUpperCase(),
        salary_period: period || null,
        description,
        tags: tagList,
        expires_at: expires ? `${expires}T23:59:59Z` : null,
        ...(initial ? {} : { status: draft ? ("draft" as const) : ("open" as const) }),
      });
    } catch (e) {
      setError(errorText(e, tr("could_not_save_the_posting")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack card" onSubmit={submit}>
      <Field label={tr("title")}>
        <TextBox required maxLength={LIMITS.title} value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <div className="row wrap">
        <Field label={tr("company")} grow>
          <TextBox required maxLength={LIMITS.company} value={company} onChange={(e) => setCompany(e.target.value)} />
        </Field>
        <Field label={tr("department")} grow>
          <TextBox maxLength={LIMITS.department} value={department} onChange={(e) => setDepartment(e.target.value)} />
        </Field>
      </div>
      <div className="row wrap">
        <Field label={tr("location")} grow>
          <TextBox maxLength={LIMITS.location} value={location} onChange={(e) => setLocation(e.target.value)} />
        </Field>
        <Field label={tr("employment_type")} grow>
          <Select value={type} onChange={(e) => setType(e.target.value as EmploymentType)}>
            {Object.entries(EMPLOYMENT_LABELS).map(([value, text]) => (
              <option key={value} value={value}>{text}</option>
            ))}
          </Select>
        </Field>
      </div>
      <CheckBox checked={remote} onChange={setRemote} label={tr("remote")} />

      <h2 style={{ margin: 0 }}>{tr("requirements")}</h2>
      <div className="row wrap">
        <Field label={tr("seniority")} grow>
          <Select value={seniority} onChange={(e) => setSeniority(e.target.value as Seniority | "")}>
            <option value="">{tr("any")}</option>
            {SENIORITIES.map((value) => (
              <option key={value} value={value}>{tr(value)}</option>
            ))}
          </Select>
        </Field>
        <Field label={tr("openings")} grow>
          <TextBox type="number" min={1} max={LIMITS.openings} inputMode="numeric" value={openings} onChange={(e) => setOpenings(e.target.value)} />
        </Field>
        <Field label={tr("experience_min_years")} grow>
          <TextBox type="number" min={0} max={LIMITS.years} inputMode="numeric" value={experience} onChange={(e) => setExperience(e.target.value)} />
        </Field>
        <Field label={tr("education_min")} grow>
          <Select value={education} onChange={(e) => setEducation(e.target.value as Education | "")}>
            <option value="">{tr("any")}</option>
            {EDUCATIONS.map((value) => (
              <option key={value} value={value}>{value === "none" ? tr("edu_none") : tr(value)}</option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label={`${tr("required_skills")} (${tr("skills_hint")})`}>
        <TextBox multiline rows={4} value={required} onChange={(e) => setRequired(e.target.value)} />
      </Field>
      <Field label={`${tr("preferred_skills")} (${tr("skills_hint")})`}>
        <TextBox multiline rows={3} value={preferred} onChange={(e) => setPreferred(e.target.value)} />
      </Field>
      <Field label={`${tr("languages")} (${tr("languages_hint")})`}>
        <TextBox multiline rows={2} value={languages} onChange={(e) => setLanguages(e.target.value)} />
      </Field>

      <div className="row wrap">
        <Field label={tr("minimum_salary")} grow>
          <TextBox type="number" min={0} inputMode="numeric" value={salaryMin} onChange={(e) => setSalaryMin(e.target.value)} />
        </Field>
        <Field label={tr("maximum_salary")} grow>
          <TextBox type="number" min={0} inputMode="numeric" value={salaryMax} onChange={(e) => setSalaryMax(e.target.value)} />
        </Field>
        <Field label={tr("currency_3_letters")} grow>
          <TextBox required minLength={3} maxLength={3} pattern="[A-Za-z]{3}" value={currency} onChange={(e) => setCurrency(e.target.value)} />
        </Field>
        <Field label={tr("salary_period")} grow>
          <Select value={period} onChange={(e) => setPeriod(e.target.value as SalaryPeriod | "")}>
            <option value="">{tr("any")}</option>
            {SALARY_PERIODS.map((value) => (
              <option key={value} value={value}>{tr(`per_${value}`)}</option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label={tr("description_plain_text")}>
        <TextBox multiline rows={8} maxLength={LIMITS.description} value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <Field label={`${tr("responsibilities")} (${tr("lines_hint")})`}>
        <TextBox multiline rows={4} value={responsibilities} onChange={(e) => setResponsibilities(e.target.value)} />
      </Field>
      <Field label={`${tr("benefits")} (${tr("lines_hint")})`}>
        <TextBox multiline rows={3} value={benefits} onChange={(e) => setBenefits(e.target.value)} />
      </Field>
      <Field label={tr("tags_comma_separated_up_to_p0", { p0: LIMITS.tags })}>
        <TextBox value={tags} onChange={(e) => setTags(e.target.value)} />
      </Field>
      <Field label={tr("expires_on_optional")}>
        <TextBox type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
      </Field>
      {!initial && <CheckBox checked={draft} onChange={setDraft} label={tr("save_as_draft")} />}
      {error && <p role="alert" className="error">{error}</p>}
      <div className="row">
        <Button disabled={busy}>{busy ? tr("saving") : submitLabel}</Button>
      </div>
    </form>
  );
}
