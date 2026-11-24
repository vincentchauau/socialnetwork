"use client";

import { useId, type CSSProperties, useCallback, useState } from "react";
import TextBox from "../elements/TextBox";
import Button from "../elements/Button";
import Select from "../elements/Select";
import { crudTr } from "./crudModel";
import { galleryTr } from "./galleryModel";

export interface SearchTerms {
  query: string;
  setQuery: (text: string) => void;
  terms: string[];
  /** The terms as the one `q` of a list request (the server splits it at commas). */
  text: string;
  commit: (text: string) => void;
  drop: (term: string) => void;
  clear: () => void;
  /** Puts exactly these terms in place of the ones there are (a saved view). */
  set: (terms: string[]) => void;
}

/** `onChange` is told whenever the set of terms changes (to go back to the first page). */
export function useSearchTerms(onChange: () => void): SearchTerms {
  const [query, setQuery] = useState("");
  const [terms, setTerms] = useState<string[]>([]);
  const commit = useCallback(
    (text: string) => {
      const added = text.split(",").map((part) => part.trim()).filter(Boolean);
      setQuery("");
      onChange();
      setTerms((previous) => [...previous, ...added.filter((term) => !previous.includes(term))]);
    },
    [onChange],
  );
  const drop = useCallback(
    (term: string) => {
      onChange();
      setTerms((previous) => previous.filter((item) => item !== term));
    },
    [onChange],
  );
  const clear = useCallback(() => {
    onChange();
    setTerms([]);
  }, [onChange]);
  const set = useCallback(
    (next: string[]) => {
      onChange();
      setQuery("");
      setTerms(next);
    },
    [onChange],
  );
  return { query, setQuery, terms, text: terms.join(","), commit, drop, clear, set };
}

/** The search box (Enter searches): one control size for the toolbar of every table and library. */
export function SearchBox({ search, controlStyle, placeholder }: { search: SearchTerms; controlStyle: CSSProperties; placeholder?: string }) {
  return (
    <form role="search" onSubmit={(event) => { event.preventDefault(); search.commit(search.query); }} style={{ display: "flex", gap: 8, alignItems: "center", flex: "1 1 240px", minWidth: 0 }}>
      <TextBox
        type="search"
        name="q"
        aria-label={crudTr("search")}
        placeholder={placeholder ?? galleryTr("search_hint")}
        value={search.query}
        onChange={(event) => (event.target.value.includes(",") ? search.commit(event.target.value) : search.setQuery(event.target.value))}
        style={{ ...controlStyle, flex: 1, minWidth: 0 }}
      />
    </form>
  );
}

/** The chips of the terms (press one to drop it), "Clear all" and how many rows match. */
export function TermChips({ search, total, ready }: { search: SearchTerms; total: number; ready: boolean }) {
  if (search.terms.length === 0) return null;
  return (
    <div role="group" aria-label={galleryTr("search_terms")} style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {search.terms.map((term) => (
        <button key={term} type="button" aria-label={galleryTr("remove_term", { term })} title={galleryTr("remove_term", { term })} onClick={() => search.drop(term)} style={{ all: "unset", cursor: "pointer", border: "1px solid color-mix(in srgb, var(--line) 35%, transparent)", borderRadius: 999, padding: "0 10px", fontSize: 13, lineHeight: "24px", background: "transparent" }}>
          {term} <span aria-hidden="true" className="muted">✕</span>
        </button>
      ))}
      <button type="button" onClick={search.clear} style={{ all: "unset", cursor: "pointer", fontSize: 13, lineHeight: "24px", textDecoration: "underline" }}>{galleryTr("clear_all")}</button>
      {ready ? <span role="status" className="muted" style={{ fontSize: 13, lineHeight: "24px", marginLeft: "auto" }}>{galleryTr("results", { total })}</span> : null}
    </div>
  );
}

export const PAGE_SIZES = [20, 50, 100]; // the server takes at most 100 rows a page

/** "20 rows per page": the same box over a table and over a grid of cards. */
export function PageSizeSelect({ value, onChange }: { value: number; onChange: (size: number) => void }) {
  const sizes = PAGE_SIZES.includes(value) ? PAGE_SIZES : [...PAGE_SIZES, value].sort((a, b) => a - b);
  return (
    <Select aria-label={crudTr("rows_per_page")} value={value} onChange={(event) => onChange(Number(event.target.value))} style={{ height: 36, boxSizing: "border-box", alignSelf: "center" }}>
      {sizes.map((size) => <option key={size} value={size}>{crudTr("n_rows_per_page", { count: size })}</option>)}
    </Select>
  );
}

/** "Select all" over the rows or cards on the page, and, with some picked, a button that deletes them. */

export interface TagBoxProps {
  label: string;
  value: string[];
  onChange: (tags: string[]) => void;
  suggestions?: string[];
  placeholder?: string;
  removeLabel?: string;
}

/** Tag editor: Enter or comma adds, Backspace on an empty box removes the last tag, suggestions filter as you type. */
export function TagBox({ label, value, onChange, suggestions = [], placeholder, removeLabel = "Remove" }: TagBoxProps) {
  const [input, setInput] = useState("");
  const inputId = useId();
  const query = input.trim().toLowerCase();
  const matches = query ? suggestions.filter((option) => option.toLowerCase().includes(query) && !value.includes(option)) : [];

  function add(tag: string) {
    const clean = tag.trim();
    if (clean && !value.includes(clean)) onChange([...value, clean]);
    setInput("");
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if ((event.key === "Enter" || event.key === ",") && input.trim()) {
      event.preventDefault();
      add(input);
    } else if (event.key === "Backspace" && !input && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  }

  return (
    <div style={{ flex: 1, minWidth: 200, position: "relative" }}>
      <label htmlFor={inputId} style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
        {label}
      </label>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, minHeight: 42, padding: 6, border: "1px solid color-mix(in srgb, var(--line) 30%, transparent)", borderRadius: 6, background: "var(--solid-0)" }}>
        {value.map((tag) => (
          <span key={tag} style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 4, background: "var(--solid-0)", fontSize: 14 }}>
            {tag}
            <Button
              type="button"
              variant="ghost"
              aria-label={`${removeLabel} ${tag}`}
              onClick={() => onChange(value.filter((existing) => existing !== tag))}
              style={{ padding: "0 4px" }}
            >
              ×
            </Button>
          </span>
        ))}
        <TextBox
          id={inputId}
          value={input}
          placeholder={placeholder}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={onKeyDown}
          style={{ flex: 1, minWidth: 80, border: "none", background: "transparent", padding: "4px 0", outline: "none" }}
        />
      </div>
      {matches.length > 0 && (
        <ul role="listbox" aria-label={label} style={{ position: "absolute", zIndex: 10, left: 0, right: 0, margin: "4px 0 0", padding: 0, maxHeight: 128, overflowY: "auto", listStyle: "none", border: "1px solid color-mix(in srgb, var(--line) 30%, transparent)", borderRadius: 6, background: "var(--solid-0)" }}>
          {matches.map((option) => (
            <li
              key={option}
              role="option"
              aria-selected={false}
              // mouse-down, not click: the input would blur first and close the list before a click lands.
              onMouseDown={(event) => {
                event.preventDefault();
                add(option);
              }}
              style={{ padding: "4px 8px", cursor: "pointer" }}
            >
              {option}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
