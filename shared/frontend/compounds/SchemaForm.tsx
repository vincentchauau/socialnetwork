"use client";

import { type FormEvent, useState } from "react";

import Alert from "../elements/Alert";
import Button from "../elements/Button";
import CheckBox from "../elements/CheckBox";
import Select from "../elements/Select";
import LabelTextBox from "./LabelTextBox";
import { NumberBox } from "./LabelTextBox";
import { TagBox } from "./InputBox";

export type FieldKind = "text" | "textarea" | "number" | "select" | "checkbox" | "tags" | "file" | "choice" | "multichoice";

/** One field of a form that is described by data (a server can send it): what it is called, what it holds, and its limits. */
export interface FieldSpec {
  name: string;
  label: string;
  kind: FieldKind;
  required?: boolean;
  /** Text: the longest text. Number: the largest number. */
  max?: number;
  min?: number;
  step?: number;
  options?: { value: string; label: string }[];
  /** A file: what the browser offers (`image/*`) and the biggest size in megabytes. */
  accept?: string;
  max_mb?: number;
  value?: string | number | boolean | string[] | null;
}

export type FormValues = Record<string, string | number | boolean | string[] | File>;

export interface SchemaFormProps {
  fields: readonly FieldSpec[];
  submitLabel: string;
  onSubmit: (values: FormValues) => void | Promise<void>;
  cancelLabel?: string;
  onCancel?: () => void;
  busy?: boolean;
  /** What went wrong the last time (the form stays as it was, to be corrected). */
  error?: string | null;
  requiredMessage?: (label: string) => string;
  tooBigMessage?: (label: string, megabytes: number) => string;
}

const emptyOf = (field: FieldSpec): string | number | boolean | string[] | File => {
  if (field.value !== undefined && field.value !== null) return field.value;
  if (field.kind === "checkbox") return false;
  if (field.kind === "tags") return [];
  if (field.kind === "number") return NaN;
  return "";
};

const isBlank = (value: unknown): boolean =>
  value === "" || (typeof value === "number" && Number.isNaN(value)) || (Array.isArray(value) && value.length === 0);

/**
 * A form made from a list of fields. It collects typed values (text, numbers, true/false, lists of tags), refuses a missing required one
 * before anything is sent, and leaves out the optional ones that were left empty, so the server's own defaults apply.
 */
export default function SchemaForm({ fields, submitLabel, onSubmit, cancelLabel, onCancel, busy = false, error = null, requiredMessage = (label) => `${label} is required`, tooBigMessage = (label, megabytes) => `${label} is bigger than ${megabytes} MB` }: SchemaFormProps) {
  const [values, setValues] = useState<FormValues>(() => Object.fromEntries(fields.map((field) => [field.name, emptyOf(field)])));
  const [missing, setMissing] = useState<string | null>(null);

  const set = (name: string, value: string | number | boolean | string[] | File) => setValues((current) => ({ ...current, [name]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    const lacking = fields.find((field) => field.required && field.kind !== "checkbox" && isBlank(values[field.name]));
    if (lacking) {
      setMissing(requiredMessage(lacking.label));
      return;
    }
    const tooBig = fields.find((field) => field.kind === "file" && field.max_mb && values[field.name] instanceof File && (values[field.name] as File).size > field.max_mb * 1024 * 1024);
    if (tooBig) {
      setMissing(tooBigMessage(tooBig.label, tooBig.max_mb ?? 0));
      return;
    }
    setMissing(null);
    const sent: FormValues = {};
    for (const field of fields) {
      const value = values[field.name];
      if (field.kind === "checkbox" || !isBlank(value)) sent[field.name] = value;
    }
    await onSubmit(sent);
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {fields.map((field) => {
        const value = values[field.name];
        if (field.kind === "checkbox") {
          return <CheckBox key={field.name} label={field.label} checked={value === true} disabled={busy} onChange={(checked) => set(field.name, checked)} />;
        }
        if (field.kind === "choice" || field.kind === "multichoice") {
          const chosen = field.kind === "choice" ? [String(value)] : Array.isArray(value) ? value : [];
          const toggle = (option: string, on: boolean) =>
            set(field.name, field.kind === "choice" ? option : on ? [...chosen, option] : chosen.filter((item) => item !== option));
          return (
            <fieldset key={field.name} disabled={busy} style={{ border: "none", padding: 0, margin: 0 }}>
              <legend style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>{field.label}</legend>
              {(field.options ?? []).map((option) => (
                <label key={option.value} style={{ display: "flex", alignItems: "center", gap: 8, padding: "2px 0" }}>
                  <input
                    type={field.kind === "choice" ? "radio" : "checkbox"}
                    name={field.name}
                    value={option.value}
                    checked={chosen.includes(option.value)}
                    onChange={(event) => toggle(option.value, event.target.checked)}
                  />
                  {option.label}
                </label>
              ))}
            </fieldset>
          );
        }
        if (field.kind === "file") {
          return (
            <label key={field.name} style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, fontWeight: 600 }}>
              {field.label}
              <input
                type="file"
                aria-label={field.label}
                accept={field.accept}
                disabled={busy}
                onChange={(event) => set(field.name, event.target.files?.[0] ?? "")}
              />
            </label>
          );
        }
        if (field.kind === "tags") {
          return <TagBox key={field.name} label={field.label} value={Array.isArray(value) ? value : []} onChange={(tags) => set(field.name, tags)} />;
        }
        if (field.kind === "number") {
          return (
            <label key={field.name} style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, fontWeight: 600 }}>
              {field.label}
              <NumberBox
                aria-label={field.label}
                value={typeof value === "number" && !Number.isNaN(value) ? value : undefined}
                min={field.min}
                max={field.max}
                step={field.step ?? 1}
                controls={false}
                disabled={busy}
                onChange={(next) => set(field.name, next)}
              />
            </label>
          );
        }
        if (field.kind === "select") {
          return (
            <label key={field.name} style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, fontWeight: 600 }}>
              {field.label}
              <Select aria-label={field.label} value={String(value)} disabled={busy} onChange={(event) => set(field.name, event.target.value)}>
                {!field.required && <option value="" />}
                {(field.options ?? []).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </Select>
            </label>
          );
        }
        return (
          <LabelTextBox
            key={field.name}
            label={field.label}
            name={field.name}
            type={field.kind === "textarea" ? "textarea" : "text"}
            rows={4}
            value={String(value ?? "")}
            required={field.required}
            disabled={busy}
            onChange={(event) => set(field.name, field.max ? event.target.value.slice(0, field.max) : event.target.value)}
          />
        );
      })}
      <Alert>{missing ?? error}</Alert>
      <div style={{ display: "flex", gap: 8 }}>
        <Button type="submit" size="sm" disabled={busy}>{submitLabel}</Button>
        {onCancel && <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={onCancel}>{cancelLabel ?? "Cancel"}</Button>}
      </div>
    </form>
  );
}
