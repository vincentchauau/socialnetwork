import { CENTER_API, apiFetch } from "@sn/api";

import { tr } from "../i18n";

/** The lists of a profile, as the server keeps them; the key of each is the name of the list. */
export type ListKey = "links" | "experience" | "education" | "skills" | "languages" | "certifications" | "projects";

export interface Profile {
  name: string | null;
  address: string | null;
  phone?: string | null;
  headline: string | null;
  summary: string | null;
  birth_date: string | null;
  city: string | null;
  region: string | null;
  country: string | null;
  avatar_url: string | null;
  links: Record<string, unknown>[];
  experience: Record<string, unknown>[];
  education: Record<string, unknown>[];
  skills: Record<string, unknown>[];
  languages: Record<string, unknown>[];
  certifications: Record<string, unknown>[];
  projects: Record<string, unknown>[];
  visibility: Record<string, string>;
}

export const getProfile = () => apiFetch<Profile>(`${CENTER_API}/auth/me/profile`);

/** Partial update: only what is in `patch` changes; `null` clears a field. */
export const saveProfile = (patch: Record<string, unknown>) =>
  apiFetch<Profile>(`${CENTER_API}/auth/me/profile`, { method: "PUT", body: JSON.stringify(patch) });

// ---- the form's own state: everything is text, so an input can hold half-typed values ----

/** The single-value fields of the form, in the order they are shown, by group. */
export const TEXT_FIELDS = [
  "name", "birth_date", "headline", "summary", "address", "city", "region", "country", "avatar_url",
] as const; // fmt: skip
export type TextField = (typeof TEXT_FIELDS)[number];

export type Row = Record<string, string>;

export interface Draft {
  text: Record<TextField, string>;
  lists: Record<ListKey, Row[]>;
  visibility: Record<string, string>;
}

export const LIST_KEYS: readonly ListKey[] = ["links", "experience", "education", "skills", "languages", "certifications", "projects"];

/** How many rows a list may hold: the same limits as the server's. */
export const LIST_MAX: Record<ListKey, number> = { links: 10, experience: 30, education: 20, skills: 50, languages: 20, certifications: 30, projects: 30 };

export const VISIBILITY_PARTS = [
  "name", "address", "birth_date", "location", "contact", "avatar", "headline",
  "summary", "links", "experience", "education", "skills", "languages", "certifications", "projects",
] as const; // fmt: skip
export const VISIBILITY_LEVELS = ["private", "employers", "public"] as const;

export interface FieldDef {
  key: string;
  label: string;
  kind?: "text" | "textarea" | "month" | "select" | "number";
  options?: { value: string; label: string }[];
  required?: boolean;
  max?: number;
}

const option = (value: string, label: string) => ({ value, label });

/** The columns of each list: what a row asks for. */
export const LIST_FIELDS: Record<ListKey, FieldDef[]> = {
  links: [
    { key: "kind", get label() { return tr("pf_loai"); }, kind: "select", get options() { return [option("linkedin", "LinkedIn"), option("github", "GitHub"), option("facebook", "Facebook"), option("portfolio", tr("pf_portfolio")), option("other", tr("pf_khac"))]; } },
    { key: "url", get label() { return tr("pf_dia_chi_web"); }, required: true, max: 300 },
    { key: "label", get label() { return tr("pf_nhan"); }, max: 60 },
  ],
  experience: [
    { key: "company", get label() { return tr("pf_cong_ty"); }, required: true, max: 100 },
    { key: "title", get label() { return tr("pf_chuc_danh"); }, required: true, max: 100 },
    { key: "type", get label() { return tr("pf_hinh_thuc"); }, kind: "select", get options() { return [option("full_time", tr("pf_toan_thoi_gian")), option("part_time", tr("pf_ban_thoi_gian")), option("contract", tr("pf_hop_dong")), option("internship", tr("pf_thuc_tap")), option("freelance", tr("pf_tu_do")), option("other", tr("pf_khac"))]; } },
    { key: "location", get label() { return tr("pf_dia_diem"); }, max: 100 },
    { key: "start", get label() { return tr("pf_bat_dau"); }, kind: "month" },
    { key: "end", get label() { return tr("pf_ket_thuc_trong_neu_dang_lam"); }, kind: "month" },
    { key: "description", get label() { return tr("pf_mo_ta"); }, kind: "textarea", max: 2000 },
  ],
  education: [
    { key: "school", get label() { return tr("pf_truong"); }, required: true, max: 100 },
    { key: "degree", get label() { return tr("pf_bang_cap"); }, max: 100 },
    { key: "field", get label() { return tr("pf_nganh_hoc"); }, max: 100 },
    { key: "start", get label() { return tr("pf_bat_dau"); }, kind: "month" },
    { key: "end", get label() { return tr("pf_ket_thuc"); }, kind: "month" },
    { key: "grade", get label() { return tr("pf_xep_loai"); }, max: 40 },
  ],
  skills: [
    { key: "name", get label() { return tr("pf_ky_nang"); }, required: true, max: 60 },
    { key: "level", get label() { return tr("pf_trinh_do"); }, kind: "select", get options() { return [option("", "—"), option("beginner", tr("pf_moi_bat_dau")), option("intermediate", tr("pf_trung_binh")), option("advanced", tr("pf_kha")), option("expert", tr("pf_chuyen_gia"))]; } },
    { key: "years", get label() { return tr("pf_so_nam"); }, kind: "number" },
  ],
  languages: [
    { key: "language", get label() { return tr("pf_ngon_ngu"); }, required: true, max: 60 },
    { key: "proficiency", get label() { return tr("pf_muc_do"); }, kind: "select", get options() { return [option("basic", tr("pf_co_ban")), option("conversational", tr("pf_giao_tiep")), option("fluent", tr("pf_thanh_thao")), option("native", tr("pf_ban_ngu"))]; } },
  ],
  certifications: [
    { key: "name", get label() { return tr("pf_ten_chung_chi"); }, required: true, max: 100 },
    { key: "issuer", get label() { return tr("pf_noi_cap"); }, max: 100 },
    { key: "issued", get label() { return tr("pf_ngay_cap"); }, kind: "month" },
    { key: "expires", get label() { return tr("pf_het_han"); }, kind: "month" },
    { key: "url", get label() { return tr("pf_dia_chi_web"); }, max: 300 },
  ],
  projects: [
    { key: "name", get label() { return tr("pf_ten_du_an"); }, required: true, max: 100 },
    { key: "role", get label() { return tr("pf_vai_tro"); }, max: 100 },
    { key: "url", get label() { return tr("pf_dia_chi_web"); }, max: 300 },
    { key: "start", get label() { return tr("pf_bat_dau"); }, kind: "month" },
    { key: "end", get label() { return tr("pf_ket_thuc"); }, kind: "month" },
    { key: "description", get label() { return tr("pf_mo_ta"); }, kind: "textarea", max: 2000 },
  ],
};

const DEFAULT_OF: Partial<Record<string, string>> = { kind: "other", type: "full_time", proficiency: "conversational" };

/** A new row: its select fields start at the server's default, the rest empty. */
export function blankRow(list: ListKey): Row {
  return Object.fromEntries(LIST_FIELDS[list].map((field) => [field.key, DEFAULT_OF[field.key] ?? ""]));
}

const text = (value: string | number | null | undefined): string => (value === null || value === undefined ? "" : String(value));

function rowsOf(list: ListKey, items: Record<string, unknown>[] | undefined): Row[] {
  return (items ?? []).map((item) => Object.fromEntries(LIST_FIELDS[list].map((field) => [field.key, text(item[field.key] as string | number | null)])));
}

/** The form's state for a profile (an empty one for someone with none). */
export function draftOf(profile: Profile | null): Draft {
  const source = profile ?? ({} as Partial<Profile>);
  const fields = Object.fromEntries(TEXT_FIELDS.map((key) => [key, text(source[key] as string | number | null | undefined)])) as Record<TextField, string>;
  const lists = Object.fromEntries(LIST_KEYS.map((key) => [key, rowsOf(key, source[key])])) as Record<ListKey, Row[]>;
  return { text: fields, lists, visibility: { ...(source.visibility ?? {}) } };
}

export class ProfileProblem extends Error {}

function itemOf(list: ListKey, row: Row): Record<string, unknown> | null {
  const filled = LIST_FIELDS[list].some((field) => (row[field.key] ?? "").trim() !== "" && DEFAULT_OF[field.key] !== row[field.key]);
  if (!filled) return null; // a row nobody typed in is dropped
  const item: Record<string, unknown> = {};
  for (const field of LIST_FIELDS[list]) {
    const value = (row[field.key] ?? "").trim();
    if (value === "") {
      if (field.required) throw new ProfileProblem(tr("pf_thieu_p0", { p0: field.label }));
      continue; // left out: the server's default (or none) applies
    }
    item[field.key] = field.kind === "number" ? Number(value) : value;
  }
  return item;
}

/** What differs between a draft and the one it started from, as a request body; `{}` when nothing changed. */
export function patchOf(draft: Draft, initial: Draft): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const key of TEXT_FIELDS) {
    if (draft.text[key].trim() === initial.text[key].trim()) continue;
    const value = draft.text[key].trim();
    if (value === "") patch[key] = null;
    else patch[key] = value;
  }
  for (const key of LIST_KEYS) {
    if (JSON.stringify(draft.lists[key]) === JSON.stringify(initial.lists[key])) continue;
    patch[key] = draft.lists[key].map((row) => itemOf(key, row)).filter((item) => item !== null);
  }
  if (JSON.stringify(draft.visibility) !== JSON.stringify(initial.visibility)) patch.visibility = draft.visibility;
  return patch;
}

const UNSAVED_KEY = "sn_profile_unsaved";

/** Registration worked but the profile did not save: say so once on the next screen. */
export function rememberProfileUnsaved(): void {
  try {
    window.sessionStorage.setItem(UNSAVED_KEY, "1");
  } catch {
    /* the notice is optional */
  }
}

export function takeProfileUnsaved(): boolean {
  try {
    const value = window.sessionStorage.getItem(UNSAVED_KEY);
    window.sessionStorage.removeItem(UNSAVED_KEY);
    return value !== null;
  } catch {
    return false;
  }
}

export const hasChanges = (draft: Draft, initial: Draft): boolean => JSON.stringify(draft) !== JSON.stringify(initial);
