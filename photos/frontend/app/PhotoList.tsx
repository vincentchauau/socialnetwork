"use client";

import { ReactNode, useCallback, useEffect, useState } from "react";

import { PhotoCard } from "./PhotoCard";
import { Photo, appendUnique, errorText, fetchPage, replacePhoto } from "./photos";

interface PhotoListProps {
  path: string;
  me: string;
  emptyText: string;
  /** Rendered above the list; receives a callback to prepend a freshly uploaded photo. */
  header?: (onUploaded: (photo: Photo) => void) => ReactNode;
}

/** Paginated list with loading / error / empty states and a "Load more" button. */
export function PhotoList({ path, me, emptyText, header }: PhotoListProps) {
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (from: number | null) => {
      setLoading(true);
      setError(null);
      try {
        const page = await fetchPage(path, from);
        setPhotos((current) => (from === null ? page.items : appendUnique(current, page.items)));
        setCursor(page.next_cursor);
        setLoaded(true);
      } catch (e) {
        setError(errorText(e, "Could not load photos"));
      } finally {
        setLoading(false);
      }
    },
    [path],
  );

  useEffect(() => {
    void load(null);
  }, [load]);

  return (
    <div className="stack">
      {header?.((photo) => setPhotos((current) => appendUnique([photo], current)))}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!loaded && loading && <p className="muted">Loading photos…</p>}
      {loaded && photos.length === 0 && <p className="muted">{emptyText}</p>}
      {photos.map((photo) => (
        <PhotoCard
          key={photo.id}
          photo={photo}
          me={me}
          onChange={(updated) => setPhotos((current) => replacePhoto(current, updated))}
          onDeleted={(id) => setPhotos((current) => current.filter((p) => p.id !== id))}
        />
      ))}
      {(cursor !== null || (error && !loaded)) && (
        <button type="button" className="secondary" disabled={loading} onClick={() => void load(loaded ? cursor : null)}>
          {loading ? "Loading…" : error ? "Retry" : "Load more"}
        </button>
      )}
    </div>
  );
}
