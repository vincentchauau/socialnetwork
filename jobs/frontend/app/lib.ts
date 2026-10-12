import { ApiError } from "@sn/api";

export const API = "/api/jobs";

export type EmploymentType = "full_time" | "part_time" | "contract" | "internship";
export type PostingStatus = "open" | "closed";
export type ApplicationStatus = "submitted" | "reviewing" | "shortlisted" | "rejected" | "hired";

export const EMPLOYMENT_LABELS: Record<EmploymentType, string> = {
  full_time: "Full time",
  part_time: "Part time",
  contract: "Contract",
  internship: "Internship",
};

export const APPLICATION_STATUSES: ApplicationStatus[] = [
  "submitted",
  "reviewing",
  "shortlisted",
  "rejected",
  "hired",
];

// Mirror the server limits so forms stop typing early; the server still validates.
export const LIMITS = {
  title: 120,
  company: 120,
  location: 120,
  description: 10_000,
  tags: 10,
  coverLetter: 5_000,
  resume: 20_000,
  email: 254,
  note: 2_000,
  headline: 120,
  skills: 20,
  about: 2_000,
  query: 100,
} as const;

export interface PostingSummary {
  id: number;
  title: string;
  company: string;
  location: string;
  remote: boolean;
  employment_type: EmploymentType;
  salary_min: number | null;
  salary_max: number | null;
  currency: string;
  snippet: string;
  tags: string[];
  status: PostingStatus;
  expired: boolean;
  expires_at: string | null;
  created_at: string;
  owner_username: string;
  is_owner: boolean;
  applied: boolean;
  saved: boolean;
  application_count: number | null;
}

export interface PostingDetail extends PostingSummary {
  description: string;
}

export interface PostingPage {
  items: PostingSummary[];
  next_cursor: string | null;
}

export interface Profile {
  username: string;
  headline: string;
  skills: string[];
  about: string;
  open_to_work: boolean;
}

export interface MyApplication {
  id: number;
  job_id: number;
  job_title: string;
  company: string;
  status: ApplicationStatus;
  cover_letter: string;
  resume_text: string;
  contact_email: string | null;
  created_at: string;
  updated_at: string;
}

export interface Applicant {
  id: number;
  job_id: number;
  applicant_username: string;
  status: ApplicationStatus;
  cover_letter: string;
  resume_text: string;
  contact_email: string | null;
  note: string;
  created_at: string;
  updated_at: string;
  profile: Profile | null;
}

export function errorText(error: unknown, fallback = "Something went wrong"): string {
  if (error instanceof ApiError) return error.message;
  return fallback;
}

export function label(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatSalary(posting: PostingSummary): string | null {
  const { salary_min: min, salary_max: max, currency } = posting;
  const fmt = (n: number) => n.toLocaleString();
  if (min !== null && max !== null) return `${fmt(min)} – ${fmt(max)} ${currency}`;
  if (min !== null) return `from ${fmt(min)} ${currency}`;
  if (max !== null) return `up to ${fmt(max)} ${currency}`;
  return null;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString();
}

export function parseTags(raw: string): string[] {
  return raw
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}
