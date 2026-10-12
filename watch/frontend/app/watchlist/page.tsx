"use client";

import { useEffect, useState } from "react";

import { ApiError, apiFetch } from "@sn/api";
import Gate from "../Gate";
import VideoList from "../VideoList";
import { API, Video } from "../types";

function Watchlist() {
  const [videos, setVideos] = useState<Video[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Video[]>(`${API}/me/watchlist`)
      .then(setVideos)
      .catch((caught: unknown) =>
        setError(caught instanceof ApiError ? caught.message : "Could not load your watchlist"),
      );
  }, []);

  if (error) {
    return (
      <p className="error" role="alert">
        {error}
      </p>
    );
  }
  if (videos === null) return <p role="status">Loading…</p>;
  return <VideoList videos={videos} empty="Your watchlist is empty." />;
}

export default function WatchlistPage() {
  return <Gate title="Watchlist">{() => <Watchlist />}</Gate>;
}
