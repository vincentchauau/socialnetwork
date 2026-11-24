import { tr } from "./i18n";
import { intlLocale } from "@sn/lib/i18n";

export const API = "/api/job";
/** The profile of the account (its resume), kept by the center: what an application can carry. */
export const PROFILE_API = "/api/center/auth/me/profile";

// The kinds of work are those of the profile of an account, so what a person looks for and what a job offers name the same things.
export type EmploymentType = "full_time" | "part_time" | "contract" | "internship" | "freelance" | "other";
export type Seniority = "intern" | "junior" | "mid" | "senior" | "lead" | "manager";
export type Education = "none" | "high_school" | "bachelor" | "master" | "doctorate";
export type SkillLevel = "beginner" | "intermediate" | "advanced" | "expert";
export type Proficiency = "basic" | "conversational" | "fluent" | "native";
export type SalaryPeriod = "hour" | "month" | "year";
export type JobStatus = "draft" | "open" | "paused" | "closed" | "filled";
export type ApplicationStatus = "submitted" | "reviewing" | "shortlisted" | "interview" | "offer" | "rejected" | "hired";

export const EMPLOYMENT_LABELS: Record<EmploymentType, string> = {
  get full_time() { return tr("full_time"); },
  get part_time() { return tr("part_time"); },
  get contract() { return tr("contract"); },
  get internship() { return tr("internship"); },
  get freelance() { return tr("freelance"); },
  get other() { return tr("other"); },
};

export const SENIORITIES: Seniority[] = ["intern", "junior", "mid", "senior", "lead", "manager"];
export const EDUCATIONS: Education[] = ["none", "high_school", "bachelor", "master", "doctorate"];
export const SALARY_PERIODS: SalaryPeriod[] = ["hour", "month", "year"];
export const JOB_STATUSES: JobStatus[] = ["draft", "open", "paused", "closed", "filled"];
const SKILL_LEVELS: SkillLevel[] = ["beginner", "intermediate", "advanced", "expert"];
const PROFICIENCIES: Proficiency[] = ["basic", "conversational", "fluent", "native"];

export const APPLICATION_STATUSES: ApplicationStatus[] = [
  "submitted",
  "reviewing",
  "shortlisted",
  "interview",
  "offer",
  "rejected",
  "hired",
];

/** Mirrors the backend map of steps an employer can take; hired and rejected are final. */
export const NEXT_STATUSES: Record<ApplicationStatus, ApplicationStatus[]> = {
  submitted: ["reviewing", "shortlisted", "rejected"],
  reviewing: ["shortlisted", "interview", "rejected", "hired"],
  shortlisted: ["interview", "offer", "hired", "rejected"],
  interview: ["offer", "hired", "rejected"],
  offer: ["hired", "rejected"],
  hired: [],
  rejected: [],
};

// Mirror the server limits so forms stop typing early; the server still validates.
export const LIMITS = {
  title: 120,
  company: 120,
  department: 120,
  location: 120,
  description: 10_000,
  tags: 10,
  coverLetter: 5_000,
  email: 254,
  note: 2_000,
  query: 100,
  requirements: 30,
  languages: 10,
  line: 300,
  openings: 1_000,
  years: 80,
  headline: 120,
  summary: 2_000,
  skills: 50,
  experience: 30,
  education: 20,
  resumeLanguages: 20,
  itemText: 2_000,
} as const;

export interface SkillItem {
  name: string;
  level: SkillLevel | null;
  years: number | null;
}

export interface LanguageItem {
  language: string;
  proficiency: Proficiency;
}

export interface JobDescriptionSummary {
  id: number;
  title: string;
  company: string;
  department: string;
  location: string;
  remote: boolean;
  employment_type: EmploymentType;
  seniority: Seniority | null;
  openings: number;
  salary_min: number | null;
  salary_max: number | null;
  currency: string;
  salary_period: SalaryPeriod | null;
  snippet: string;
  tags: string[];
  status: JobStatus;
  expired: boolean;
  expires_at: string | null;
  created_at: string;
  owner_username: string;
  is_owner: boolean;
  applied: boolean;
  saved: boolean;
  application_count: number | null;
}

/** How well a person fits what a job asks of skills (`score` is 0 to 100; absent when the job asks for none). */
export interface Match {
  score: number | null;
  matched: string[];
  partial: string[];
  missing: string[];
  missing_preferred: string[];
}

export interface JobDescriptionDetail extends JobDescriptionSummary {
  match: Match | null;
  description: string;
  experience_min_years: number | null;
  education_min: Education | null;
  skills_required: SkillItem[];
  skills_preferred: SkillItem[];
  languages: LanguageItem[];
  responsibilities: string[];
  benefits: string[];
}

export interface JobDescriptionPage {
  items: JobDescriptionSummary[];
  next_cursor: string | null;
}

export interface ExperienceItem {
  company: string;
  title: string;
  start: string | null;
  end: string | null;
  description: string;
}

export interface EducationItem {
  school: string;
  degree: string;
  field: string;
  start: string | null;
  end: string | null;
}

/** The resume of a person as it was when they applied: what they chose to show from the profile of their account. */
export interface Resume {
  headline: string;
  summary: string;
  skills: SkillItem[];
  experience: ExperienceItem[];
  education: EducationItem[];
  languages: LanguageItem[];
}

export interface Step {
  status: string;
  at: string;
  by: "applicant" | "employer";
}

export interface MyApplication {
  id: number;
  job_id: number;
  job_title: string;
  company: string;
  status: ApplicationStatus;
  cover_letter: string;
  resume: Resume | null;
  contact_email: string | null;
  history: Step[];
  created_at: string;
  updated_at: string;
}

export interface Applicant {
  id: number;
  job_id: number;
  applicant_username: string;
  status: ApplicationStatus;
  cover_letter: string;
  resume: Resume | null;
  contact_email: string | null;
  note: string;
  match: Match | null;
  history: Step[];
  created_at: string;
  updated_at: string;
}

export { errorText } from "@sn/api";

export function label(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatSalary(job: JobDescriptionSummary): string | null {
  const { salary_min: min, salary_max: max, currency, salary_period: period } = job;
  const fmt = (n: number) => n.toLocaleString(intlLocale());
  const per = period ? ` / ${tr(`per_${period}`)}` : "";
  if (min !== null && max !== null) return tr("p0_p1_currency", { p0: fmt(min), p1: fmt(max), currency }) + per;
  if (min !== null) return tr("from_p0_currency", { p0: fmt(min), currency }) + per;
  if (max !== null) return tr("up_to_p0_currency", { p0: fmt(max), currency }) + per;
  return null;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(intlLocale());
}

export function parseTags(raw: string): string[] {
  return raw
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

/** The lines of a text box, without the empty ones. */
export function parseLines(raw: string): string[] {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function linesToText(lines: readonly string[]): string {
  return lines.join("\n");
}

const isLevel = (value: string): value is SkillLevel => (SKILL_LEVELS as string[]).includes(value);
const isProficiency = (value: string): value is Proficiency => (PROFICIENCIES as string[]).includes(value);

/** Skills as lines: `Python`, or `Python, advanced, 4` with a level and the years. A part that is not a level or a number is ignored. */
export function parseSkills(raw: string): SkillItem[] {
  return parseLines(raw).map((line) => {
    const [name, ...rest] = line.split(",").map((part) => part.trim());
    const level = rest.find(isLevel) ?? null;
    const years = rest.map(Number).find((n) => Number.isInteger(n) && n >= 0 && n <= LIMITS.years) ?? null;
    return { name, level, years };
  });
}

function skillToText(skill: SkillItem): string {
  return [skill.name, skill.level, skill.years === null ? null : String(skill.years)].filter((part) => part !== null).join(", ");
}

export function skillsToText(skills: readonly SkillItem[]): string {
  return skills.map(skillToText).join("\n");
}

/** Languages as lines: `English`, or `English, fluent`. */
export function parseLanguages(raw: string): LanguageItem[] {
  return parseLines(raw).map((line) => {
    const [language, proficiency = ""] = line.split(",").map((part) => part.trim());
    return { language, proficiency: isProficiency(proficiency) ? proficiency : "conversational" };
  });
}

export function languagesToText(languages: readonly LanguageItem[]): string {
  return languages.map((item) => `${item.language}, ${item.proficiency}`).join("\n");
}

function clip(value: unknown, max: number): string {
  return typeof value === "string" ? value.slice(0, max) : "";
}

function dateOf(value: unknown): string | null {
  return typeof value === "string" && value ? value.slice(0, 10) : null;
}

/** The resume that an application carries, taken from the profile of the account (anything the profile lacks is empty, anything too long is cut). */
export function resumeFromProfile(profile: Record<string, unknown>): Resume {
  const list = (key: string, max: number): Record<string, unknown>[] =>
    (Array.isArray(profile[key]) ? (profile[key] as Record<string, unknown>[]) : []).slice(0, max);
  const level = (value: unknown): SkillLevel | null => (typeof value === "string" && isLevel(value) ? value : null);
  const years = (value: unknown): number | null =>
    typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= LIMITS.years ? value : null;
  return {
    headline: clip(profile.headline, LIMITS.headline),
    summary: clip(profile.summary, LIMITS.summary),
    skills: list("skills", LIMITS.skills)
      .filter((item) => typeof item.name === "string" && item.name)
      .map((item) => ({ name: clip(item.name, 60), level: level(item.level), years: years(item.years) })),
    experience: list("experience", LIMITS.experience).map((item) => ({
      company: clip(item.company, 120),
      title: clip(item.title, 120),
      start: dateOf(item.start),
      end: dateOf(item.end),
      description: clip(item.description, LIMITS.itemText),
    })),
    education: list("education", LIMITS.education).map((item) => ({
      school: clip(item.school, 120),
      degree: clip(item.degree, 120),
      field: clip(item.field, 120),
      start: dateOf(item.start),
      end: dateOf(item.end),
    })),
    languages: list("languages", LIMITS.resumeLanguages)
      .filter((item) => typeof item.language === "string" && item.language)
      .map((item) => ({
        language: clip(item.language, 60),
        proficiency: typeof item.proficiency === "string" && isProficiency(item.proficiency) ? item.proficiency : "conversational",
      })),
  };
}

/** Is there anything in the resume worth sending? */
export function hasResume(resume: Resume): boolean {
  return Boolean(resume.headline || resume.summary || resume.skills.length || resume.experience.length || resume.education.length || resume.languages.length);
}
