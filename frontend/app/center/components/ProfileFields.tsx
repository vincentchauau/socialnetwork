"use client";

import { useId } from "react";

import { INPUT, LABEL, NOTE, SECONDARY_BUTTON } from "./ui";
import { tr } from "../i18n";
import {
  type Draft,
  type FieldDef,
  LIST_FIELDS,
  LIST_KEYS,
  LIST_MAX,
  type ListKey,
  type Row,
  type TextField,
  VISIBILITY_LEVELS,
  VISIBILITY_PARTS,
  blankRow,
} from "../lib/profile";
import Button from "@sn/elements/Button";
import TextBox from "@sn/elements/TextBox";
import Select from "@sn/elements/Select";

interface Props {
  draft: Draft;
  onChange: (next: Draft) => void;
}

const LIST_TITLE: Record<ListKey, () => string> = {
  links: () => tr("pf_lien_ket"),
  experience: () => tr("pf_kinh_nghiem_lam_viec"),
  education: () => tr("pf_hoc_van"),
  skills: () => tr("pf_ky_nang_2"),
  languages: () => tr("pf_ngon_ngu_2"),
  certifications: () => tr("pf_chung_chi"),
  projects: () => tr("pf_du_an"),
};

const levelLabel = (level: string): string => ({ private: tr("pf_rieng_tu"), employers: tr("pf_nha_tuyen_dung"), public: tr("pf_cong_khai") })[level] ?? level;

const partLabel = (part: string): string => tr(`pf_phan_${part}`);

interface TextDef {
  key: TextField;
  label: () => string;
  kind?: "text" | "textarea" | "date" | "url";
  max?: number;
}

const GROUPS: { title: () => string; fields: TextDef[] }[] = [
  {
    title: () => tr("pf_thong_tin_ca_nhan"),
    fields: [
      { key: "name", label: () => tr("pf_ho_va_ten"), max: 100 },
      { key: "birth_date", label: () => tr("pf_ngay_sinh"), kind: "date" },
      { key: "headline", label: () => tr("pf_gioi_thieu_ngan_mot_dong"), max: 120 },
      { key: "summary", label: () => tr("pf_tom_tat_ban_than"), kind: "textarea", max: 5000 },
    ],
  },
  {
    title: () => tr("pf_dia_chi_va_lien_he"),
    fields: [
      { key: "address", label: () => tr("pf_dia_chi"), max: 255 },
      { key: "city", label: () => tr("pf_thanh_pho"), max: 80 },
      { key: "region", label: () => tr("pf_tinh_quan"), max: 80 },
      { key: "country", label: () => tr("pf_quoc_gia"), max: 80 },
      { key: "avatar_url", label: () => tr("pf_lien_ket_anh_dai_dien"), kind: "url", max: 255 },
    ],
  },
];

function TextControl({ id, def, value, onChange }: { id: string; def: TextDef; value: string; onChange: (value: string) => void }) {
  if (def.kind === "textarea") {
    return <TextBox multiline id={id} value={value} maxLength={def.max} rows={4} onChange={(e) => onChange(e.target.value)} className={INPUT} />;
  }
  const type = def.kind === "date" ? "date" : def.kind === "url" ? "url" : "text";
  return (
    <TextBox id={id} type={type} value={value} maxLength={def.max}
           onChange={(e) => onChange(e.target.value)} className={INPUT} />
  );
}

function CellControl({ id, def, value, onChange }: { id: string; def: FieldDef; value: string; onChange: (value: string) => void }) {
  if (def.kind === "textarea") return <TextBox multiline id={id} value={value} maxLength={def.max} rows={3} onChange={(e) => onChange(e.target.value)} className={INPUT} />;
  if (def.kind === "select") {
    return (
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={INPUT}>
        {def.options?.map((item) => (
          <option key={item.value} value={item.value}>{item.label}</option>
        ))}
      </Select>
    );
  }
  const type = def.kind === "month" ? "month" : def.kind === "number" ? "number" : "text";
  return <TextBox id={id} type={type} value={value} maxLength={def.max} min={def.kind === "number" ? 0 : undefined} max={def.kind === "number" ? 80 : undefined}
                onChange={(e) => onChange(e.target.value)} className={INPUT} />;
}

/** The rows of one list: each with its fields, a button to remove it, and one to add another. */
function ListEditor({ list, rows, onChange }: { list: ListKey; rows: Row[]; onChange: (rows: Row[]) => void }) {
  const base = useId();
  const fields = LIST_FIELDS[list];
  const setCell = (index: number, key: string, value: string) => onChange(rows.map((row, i) => (i === index ? { ...row, [key]: value } : row)));
  return (
    <details className="border rounded p-2 mb-2">
      <summary className="font-medium cursor-pointer">
        {LIST_TITLE[list]()} ({rows.length})
      </summary>
      <div role="group" aria-label={LIST_TITLE[list]()} className="mt-2">
        {rows.length === 0 && <p className={NOTE}>{tr("pf_chua_co_muc_nao")}</p>}
        {rows.map((row, index) => (
          <fieldset key={index} className="border rounded p-2 mb-2">
            <legend className="text-sm px-1">{LIST_TITLE[list]()} {index + 1}</legend>
            {fields.map((field) => {
              const id = `${base}-${index}-${field.key}`;
              return (
                <div key={field.key}>
                  <label htmlFor={id} className={LABEL}>{field.label}{field.required ? " *" : ""}</label>
                  <CellControl id={id} def={field} value={row[field.key] ?? ""} onChange={(value) => setCell(index, field.key, value)} />
                </div>
              );
            })}
            <Button type="button" variant="secondary" className={SECONDARY_BUTTON} onClick={() => onChange(rows.filter((_, i) => i !== index))}>
              {tr("pf_xoa_muc_p0", { p0: `${LIST_TITLE[list]()} ${index + 1}` })}
            </Button>
          </fieldset>
        ))}
        <Button type="button" variant="secondary" disabled={rows.length >= LIST_MAX[list]} className={SECONDARY_BUTTON}
                onClick={() => onChange([...rows, blankRow(list)])}>
          {tr("pf_them_p0", { p0: LIST_TITLE[list]() })}
        </Button>
      </div>
    </details>
  );
}

/** Every field of the profile, controlled by `draft`; it keeps no state of its own. */
export default function ProfileFields({ draft, onChange }: Props) {
  const base = useId();
  const setText = (key: TextField, value: string) => onChange({ ...draft, text: { ...draft.text, [key]: value } });
  return (
    <>
      {GROUPS.map((group) => (
        <details key={group.title()} open={group === GROUPS[0]} className="border rounded p-2 mb-2">
          <summary className="font-medium cursor-pointer">{group.title()}</summary>
          <div role="group" aria-label={group.title()} className="mt-2">
            {group.fields.map((def) => (
              <div key={def.key}>
                <label htmlFor={`${base}-${def.key}`} className={LABEL}>{def.label()}</label>
                <TextControl id={`${base}-${def.key}`} def={def} value={draft.text[def.key]} onChange={(value) => setText(def.key, value)} />
              </div>
            ))}
          </div>
        </details>
      ))}
      {LIST_KEYS.map((list) => (
        <ListEditor key={list} list={list} rows={draft.lists[list]} onChange={(rows) => onChange({ ...draft, lists: { ...draft.lists, [list]: rows } })} />
      ))}
      <details className="border rounded p-2 mb-2">
        <summary className="font-medium cursor-pointer">{tr("pf_quyen_rieng_tu")}</summary>
        <div role="group" aria-label={tr("pf_quyen_rieng_tu")} className="mt-2">
          <p className={NOTE}>{tr("pf_moi_muc_mac_dinh_la_rieng_tu")}</p>
          {VISIBILITY_PARTS.map((part) => (
            <div key={part}>
              <label htmlFor={`${base}-vis-${part}`} className={LABEL}>{partLabel(part)}</label>
              <Select id={`${base}-vis-${part}`} value={draft.visibility[part] ?? "private"} className={INPUT}
                      onChange={(e) => onChange({ ...draft, visibility: { ...draft.visibility, [part]: e.target.value } })}>
                {VISIBILITY_LEVELS.map((level) => (
                  <option key={level} value={level}>{levelLabel(level)}</option>
                ))}
              </Select>
            </div>
          ))}
        </div>
      </details>
    </>
  );
}
