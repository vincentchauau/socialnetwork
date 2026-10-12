"use client";

import { FormEvent, useEffect, useState } from "react";

import { MAX_TEXT_CHARS, Photo, PhotoComment, deleteComment, errorText, fetchComments, postComment } from "./photos";

interface CommentsProps {
  photo: Photo;
  me: string;
  onCountChange: (count: number) => void;
}

export function Comments({ photo, me, onCountChange }: CommentsProps) {
  const [comments, setComments] = useState<PhotoComment[] | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchComments(photo.id)
      .then((list) => !cancelled && setComments(list))
      .catch((e: unknown) => !cancelled && setError(errorText(e, "Could not load comments")));
    return () => {
      cancelled = true;
    };
  }, [photo.id]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await postComment(photo.id, content);
      const next = [...(comments ?? []), created];
      setComments(next);
      onCountChange(next.length);
      setDraft("");
    } catch (e) {
      setError(errorText(e, "Could not post comment"));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    setError(null);
    try {
      await deleteComment(id);
      const next = (comments ?? []).filter((comment) => comment.id !== id);
      setComments(next);
      onCountChange(next.length);
    } catch (e) {
      setError(errorText(e, "Could not delete comment"));
    }
  }

  return (
    <section className="stack" aria-label={`Comments on photo ${photo.id}`}>
      {comments === null && !error && <p className="muted">Loading comments…</p>}
      {comments?.length === 0 && <p className="muted">No comments yet.</p>}
      {comments && comments.length > 0 && (
        <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {comments.map((comment) => (
            <li key={comment.id} style={{ overflowWrap: "anywhere" }}>
              <strong>{comment.username}</strong> {comment.content}{" "}
              {(photo.is_mine || comment.username === me) && (
                <button
                  type="button"
                  className="secondary"
                  aria-label={`Delete comment by ${comment.username}`}
                  onClick={() => void remove(comment.id)}
                >
                  ✕
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <form className="row" onSubmit={submit}>
        <label htmlFor={`comment-${photo.id}`} className="muted" style={{ position: "absolute", left: -9999 }}>
          Add a comment
        </label>
        <input
          id={`comment-${photo.id}`}
          value={draft}
          maxLength={MAX_TEXT_CHARS}
          placeholder="Add a comment"
          onChange={(event) => setDraft(event.target.value)}
        />
        <button type="submit" disabled={busy || !draft.trim()}>
          Post
        </button>
      </form>
    </section>
  );
}
