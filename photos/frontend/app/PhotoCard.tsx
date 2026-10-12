"use client";

import { useState } from "react";

import { Comments } from "./Comments";
import { API, Photo, deletePhoto, errorText, setLike } from "./photos";

interface PhotoCardProps {
  photo: Photo;
  me: string;
  onChange: (photo: Photo) => void;
  onDeleted: (id: number) => void;
}

export function PhotoCard({ photo, me, onChange, onDeleted }: PhotoCardProps) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showComments, setShowComments] = useState(false);

  async function toggleLike() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const state = await setLike(photo.id, !photo.liked_by_me);
      onChange({ ...photo, liked_by_me: state.liked, like_count: state.like_count });
    } catch (e) {
      setError(errorText(e, "Could not update like"));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (busy || !window.confirm("Delete this photo?")) return;
    setBusy(true);
    setError(null);
    try {
      await deletePhoto(photo.id);
      onDeleted(photo.id);
    } catch (e) {
      setError(errorText(e, "Could not delete photo"));
      setBusy(false);
    }
  }

  return (
    <article className="card stack" aria-label={`Photo by ${photo.username}`}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <a href={`/photos/u/${encodeURIComponent(photo.username)}`}>{photo.username}</a>
        <time className="muted" dateTime={photo.created_at}>
          {new Date(photo.created_at).toLocaleString()}
        </time>
      </div>
      <img
        src={`${API}${photo.image_url}`}
        alt={photo.caption ?? `Photo by ${photo.username}`}
        width={photo.width}
        height={photo.height}
        loading="lazy"
        style={{ maxWidth: "100%", height: "auto", borderRadius: 4 }}
      />
      {photo.caption && <p style={{ margin: 0, overflowWrap: "anywhere" }}>{photo.caption}</p>}
      <div className="row" style={{ flexWrap: "wrap" }}>
        <button type="button" aria-pressed={photo.liked_by_me} disabled={busy} onClick={() => void toggleLike()}>
          {photo.liked_by_me ? "♥ Liked" : "♡ Like"} ({photo.like_count})
        </button>
        <button
          type="button"
          className="secondary"
          aria-expanded={showComments}
          onClick={() => setShowComments((open) => !open)}
        >
          Comments ({photo.comment_count})
        </button>
        {photo.is_mine && (
          <button type="button" className="secondary" disabled={busy} onClick={() => void remove()}>
            Delete
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {showComments && (
        <Comments
          photo={photo}
          me={me}
          onCountChange={(count) => onChange({ ...photo, comment_count: count })}
        />
      )}
    </article>
  );
}
