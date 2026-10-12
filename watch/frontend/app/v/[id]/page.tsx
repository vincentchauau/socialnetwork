"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, User, apiFetch } from "@sn/api";
import Gate from "../../Gate";
import { formatSize, resumePosition, shouldSaveProgress } from "../../format";
import { API, VideoDetail } from "../../types";

function Player({ videoId, user }: { videoId: number; user: User }) {
  const [video, setVideo] = useState<VideoDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [deleted, setDeleted] = useState(false);
  const lastSaved = useRef(0);
  const resumeFrom = useRef(0);
  const elementRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    apiFetch<VideoDetail>(`${API}/videos/${videoId}`)
      .then((detail) => {
        resumeFrom.current = detail.progress_seconds;
        setVideo(detail);
      })
      .catch((caught: unknown) =>
        setError(caught instanceof ApiError ? caught.message : "Could not load this video"),
      );
  }, [videoId]);

  const saveProgress = useCallback(
    (force: boolean) => {
      const element = elementRef.current;
      if (!element || element.currentTime <= 0) return;
      const now = Date.now();
      if (!force && !shouldSaveProgress(now, lastSaved.current)) return;
      lastSaved.current = now;
      apiFetch(`${API}/videos/${videoId}/progress`, {
        method: "PUT",
        body: JSON.stringify({ seconds: element.currentTime }),
      }).catch(() => setNotice("Could not save your progress."));
    },
    [videoId],
  );

  // Save once more when the viewer leaves the page.
  useEffect(() => () => saveProgress(true), [saveProgress]);

  function onLoadedMetadata() {
    const element = elementRef.current;
    if (!element) return;
    const position = resumePosition(resumeFrom.current, element.duration);
    if (position > 0) element.currentTime = position;
  }

  async function toggleWatchlist(current: VideoDetail) {
    setNotice(null);
    try {
      await apiFetch(`${API}/videos/${videoId}/watchlist`, {
        method: current.in_watchlist ? "DELETE" : "PUT",
      });
      setVideo({ ...current, in_watchlist: !current.in_watchlist });
    } catch (caught) {
      setNotice(caught instanceof ApiError ? caught.message : "Could not update your watchlist");
    }
  }

  async function remove() {
    if (!window.confirm("Delete this video permanently?")) return;
    setNotice(null);
    try {
      await apiFetch(`${API}/videos/${videoId}`, { method: "DELETE" });
      elementRef.current?.pause();
      setDeleted(true);
    } catch (caught) {
      setNotice(caught instanceof ApiError ? caught.message : "Could not delete the video");
    }
  }

  if (error) {
    return (
      <p className="error" role="alert">
        {error}
      </p>
    );
  }
  if (deleted) return <p role="status">Video deleted.</p>;
  if (!video) return <p role="status">Loading…</p>;

  return (
    <article className="stack">
      <h2 style={{ margin: 0 }}>{video.title}</h2>
      <video
        ref={elementRef}
        className="player"
        controls
        preload="metadata"
        src={`${API}/videos/${videoId}/stream`}
        aria-label={video.title}
        onLoadedMetadata={onLoadedMetadata}
        onTimeUpdate={() => saveProgress(false)}
        onPause={() => saveProgress(true)}
        onEnded={() => saveProgress(true)}
      >
        Your browser cannot play this video.
      </video>
      <p className="muted">
        {video.owner} · {video.views} {video.views === 1 ? "view" : "views"} ·{" "}
        {formatSize(video.size_bytes)}
      </p>
      {video.tags.length > 0 && (
        <ul className="tags" aria-label="Tags">
          {video.tags.map((tag) => (
            <li key={tag} className="tag">
              {tag}
            </li>
          ))}
        </ul>
      )}
      {video.description && <p className="desc">{video.description}</p>}
      <div className="row wrap">
        <button
          type="button"
          className="secondary"
          aria-pressed={video.in_watchlist}
          onClick={() => void toggleWatchlist(video)}
        >
          {video.in_watchlist ? "Remove from watchlist" : "Add to watchlist"}
        </button>
        {video.owner_id === user.id && (
          <button type="button" className="secondary" onClick={() => void remove()}>
            Delete video
          </button>
        )}
      </div>
      {notice && (
        <p className="error" role="alert">
          {notice}
        </p>
      )}
    </article>
  );
}

export default function WatchVideoPage() {
  const params = useParams<{ id: string }>();
  const videoId = Number(params.id);
  const valid = Number.isInteger(videoId) && videoId > 0;
  return (
    <Gate title="Watch">
      {(user) =>
        valid ? (
          <Player videoId={videoId} user={user} />
        ) : (
          <p className="error" role="alert">
            Invalid video link.
          </p>
        )
      }
    </Gate>
  );
}
