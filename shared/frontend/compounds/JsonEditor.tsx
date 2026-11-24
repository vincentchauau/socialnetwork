"use client";

import { crudTr } from "./crudModel";

interface Props {
  /** The json as text (what the person sees and types). */
  value: string;
  onChange?: (text: string) => void;
  /** Read-only shows the formatted json only, with a copy button. */
  readOnly?: boolean;
  disabled?: boolean;
  /** The name of the column, for the error message. */
  label: string;
}

/** The problem with a json text, or null when it is valid (an empty text is valid: it means no value). */
export function jsonProblem(text: string, label: string): string | null {
  if (text.trim() === "") return null;
  try {
    JSON.parse(text);
    return null;
  } catch {
    return crudTr("invalid_json", { name: label });
  }
}

/** A json value you can read and edit: the text in a monospace box, and a message when it is not valid json. */
export default function JsonEditor({ value, onChange, readOnly = false, disabled = false, label }: Props) {
  if (readOnly) {
    return (
      <pre aria-label={label} style={{ margin: 0, fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{value}</pre>
    );
  }
  const problem = jsonProblem(value, label);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <textarea
        aria-label={label}
        value={value}
        disabled={disabled}
        spellCheck={false}
        rows={8}
        onChange={(event) => onChange?.(event.target.value)}
        style={{ width: "100%", boxSizing: "border-box", fontFamily: "ui-monospace, Consolas, monospace", fontSize: 12, padding: 8, background: "color-mix(in srgb, var(--line) 8%, transparent)", color: "inherit", border: "1px solid color-mix(in srgb, var(--line) 30%, transparent)", borderRadius: 6 }}
      />
      {problem ? <p role="alert" style={{ margin: 0 }}>{problem}</p> : null}
    </div>
  );
}
