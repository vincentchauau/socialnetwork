"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

import { apiFetch, errorText } from "../api";
import { registerScoped } from "../lib/i18n";
import Button from "../elements/Button";
import Select from "../elements/Select";
import TextBox from "../elements/TextBox";
import { confirmDialog } from "./Dialogs";
import bundles from "./comments.locales.json";

const tr = registerScoped("comments", bundles);

export interface CommentItem {
  id: number;
  object_id: number;
  username: string;
  content: string;
  rating: number | null;
  created_at: string;
  edited_at: string | null;
}

export type RatingMode = "none" | "optional" | "required";

export interface CommentsProps {
  /** Where the comments of this thing are: `/api/photo/photos/7/comments`. */
  collection: string;
  /** Where one comment is, without its id: `/api/photo/comments` (the id is added). */
  item: string;
  /** My username: only my own comments are changed. */
  me: string;
  /** Is this a thing of mine? Then I may delete what others said. */
  canModerate?: boolean;
  /** Stars: none, there may be one, or one has to be given. */
  rating?: RatingMode;
  /** Names the section for a screen reader. */
  label: string;
  maxLength?: number;
  /** Show the newest first (reviews) instead of last (a conversation). */
  newestFirst?: boolean;
  /** Ask this before a comment is deleted. */
  confirmDelete?: string;
  /** A text to ask for what to write, when it is not "Add a comment". */
  placeholder?: string;
  /** Called with how many comments there are after a change. */
  onCountChange?: (count: number) => void;
  /** Called after a comment was posted, changed or deleted (the page may show new stars). */
  onChanged?: () => void;
}

const STARS = [5, 4, 3, 2, 1];

export function Stars({ value }: { value: number }) {
  return (
    <span role="img" aria-label={tr("out_of_5", { p0: value })}>
      {"★".repeat(value)}
      {"☆".repeat(Math.max(0, 5 - value))}
    </span>
  );
}

/** What people say about a thing, and the stars they give it: the same everywhere (the server side is `sn_shared.comments`). */
export default function Comments({
  collection, item, me, canModerate = false, rating = "none", label, maxLength = 1000, newestFirst = false, confirmDelete, placeholder, onCountChange, onChanged,
}: CommentsProps) {
  const [items, setItems] = useState<CommentItem[] | null>(null);
  const [draft, setDraft] = useState("");
  const [stars, setStars] = useState(rating === "required" ? "5" : "");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<CommentItem | null>(null);

  const load = useCallback(() => apiFetch<CommentItem[]>(collection), [collection]);

  useEffect(() => {
    let cancelled = false;
    load()
      .then((list) => !cancelled && setItems(list))
      .catch((caught: unknown) => !cancelled && setError(errorText(caught, tr("could_not_load"))));
    return () => {
      cancelled = true;
    };
  }, [load]);

  function changed(next: CommentItem[]) {
    setItems(next);
    onCountChange?.(next.length);
    onChanged?.();
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (busy || (!content && !stars)) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const body: Record<string, unknown> = { content };
      if (rating !== "none" && stars) body.rating = Number(stars);
      const created = await apiFetch<CommentItem>(collection, { method: "POST", body: JSON.stringify(body) });
      changed(newestFirst ? [created, ...(items ?? [])] : [...(items ?? []), created]);
      setDraft("");
      setMessage(tr("thanks"));
    } catch (caught) {
      setError(errorText(caught, tr("could_not_post")));
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!editing || busy) return;
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { content: editing.content.trim() };
      if (rating !== "none") body.rating = editing.rating;
      const saved = await apiFetch<CommentItem>(`${item}/${editing.id}`, { method: "PATCH", body: JSON.stringify(body) });
      changed((items ?? []).map((row) => (row.id === saved.id ? saved : row)));
      setEditing(null);
    } catch (caught) {
      setError(errorText(caught, tr("could_not_update")));
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: CommentItem) {
    if (confirmDelete && !(await confirmDialog(confirmDelete))) return;
    setError(null);
    try {
      await apiFetch(`${item}/${row.id}`, { method: "DELETE" });
      changed((items ?? []).filter((other) => other.id !== row.id));
    } catch (caught) {
      setError(errorText(caught, tr("could_not_delete")));
    }
  }

  const starOptions = (
    <>
      {rating === "optional" && <option value="">{tr("no_rating")}</option>}
      {STARS.map((value) => (
        <option key={value} value={value}>{"★".repeat(value)} {value} / 5</option>
      ))}
    </>
  );

  return (
    <section className="stack" aria-label={label}>
      {items === null && !error && <p className="muted">{tr("loading")}</p>}
      {items?.length === 0 && <p className="muted">{tr("none_yet")}</p>}
      {items && items.length > 0 && (
        <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {items.map((row) => (
            <li key={row.id} style={{ overflowWrap: "anywhere" }}>
              <strong>{row.username}</strong>{" "}
              {row.rating !== null && <Stars value={row.rating} />}{" "}
              <span className="muted">{new Date(row.created_at).toLocaleDateString()}{row.edited_at ? ` · ${tr("edited")}` : ""}</span>
              {editing?.id === row.id ? (
                <form className="stack" onSubmit={(event) => void saveEdit(event)} aria-label={tr("edit_by_p0", { p0: row.username })}>
                  {rating !== "none" && (
                    <Select aria-label={tr("rating")} value={editing.rating ?? ""} onChange={(event) => setEditing({ ...editing, rating: event.target.value ? Number(event.target.value) : null })}>
                      {starOptions}
                    </Select>
                  )}
                  <TextBox multiline rows={3} aria-label={tr("edit_by_p0", { p0: row.username })} value={editing.content} maxLength={maxLength} onChange={(event) => setEditing({ ...editing, content: event.target.value })} />
                  <div className="row">
                    <Button type="submit" size="sm" disabled={busy}>{tr("save")}</Button>
                    <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={() => setEditing(null)}>{tr("cancel")}</Button>
                  </div>
                </form>
              ) : (
                <div style={{ whiteSpace: "pre-wrap" }}>{row.content}</div>
              )}
              {editing?.id !== row.id && (
                <div className="row">
                  {row.username === me && (
                    <Button type="button" size="sm" variant="secondary" aria-label={tr("edit_by_p0", { p0: row.username })} onClick={() => setEditing(row)}>{tr("edit")}</Button>
                  )}
                  {(canModerate || row.username === me) && (
                    <Button type="button" size="sm" variant="secondary" aria-label={tr("delete_by_p0", { p0: row.username })} onClick={() => void remove(row)}>{tr("delete")}</Button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && <p role="alert" className="error">{error}</p>}
      {message && !error && <p role="status" className="muted">{message}</p>}
      <form className="stack" onSubmit={(event) => void submit(event)}>
        {rating !== "none" && (
          <label className="stack" style={{ gap: 4 }}>
            {tr("rating")}
            <Select value={stars} onChange={(event) => setStars(event.target.value)}>
              {starOptions}
            </Select>
          </label>
        )}
        <TextBox multiline rows={3} aria-label={placeholder ?? tr("add")} placeholder={placeholder ?? tr("add")} value={draft} maxLength={maxLength} onChange={(event) => setDraft(event.target.value)} />
        <div className="row">
          <Button type="submit" loading={busy} loadingLabel={tr("posting")} disabled={busy || (!draft.trim() && !stars)}>{tr("post")}</Button>
        </div>
      </form>
    </section>
  );
}
