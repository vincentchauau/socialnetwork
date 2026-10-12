"use client";

import { FormEvent, useState } from "react";

import { ApiError } from "@sn/api";
import Gate from "../Gate";
import { parseTags, validateTags } from "../format";
import { API, Video } from "../types";

async function errorFrom(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return "Please check the fields and try again";
  } catch {
    // body was not JSON
  }
  return `Upload failed (${response.status})`;
}

function UploadForm() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tagsInput, setTagsInput] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [rights, setRights] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Video | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const tags = parseTags(tagsInput);
    const tagProblem = validateTags(tags);
    if (tagProblem) return setError(tagProblem);
    if (!file) return setError("Choose a video file");
    if (!rights) return setError("Please confirm you have the rights to share this video");

    const form = new FormData();
    form.append("file", file);
    form.append("title", title.trim());
    form.append("description", description);
    form.append("rights_confirmed", "true");
    tags.forEach((tag) => form.append("tags", tag));

    setBusy(true);
    try {
      const response = await fetch(`${API}/videos`, {
        method: "POST",
        credentials: "include",
        body: form,
      });
      if (response.status === 401) throw new ApiError(401, "Please sign in again");
      if (!response.ok) throw new ApiError(response.status, await errorFrom(response));
      setCreated((await response.json()) as Video);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Upload failed. Check your connection.");
    } finally {
      setBusy(false);
    }
  }

  if (created) {
    return (
      <div className="card stack" role="status">
        <p>Uploaded “{created.title}”.</p>
        <a href={`/watch/v/${created.id}`}>Watch it now</a>
      </div>
    );
  }

  return (
    <form className="stack card" onSubmit={onSubmit}>
      <label htmlFor="file">Video file (MP4 or WebM)</label>
      <input
        id="file"
        type="file"
        accept="video/mp4,video/webm"
        required
        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
      />
      <label htmlFor="title">Title</label>
      <input
        id="title"
        value={title}
        required
        maxLength={120}
        onChange={(event) => setTitle(event.target.value)}
      />
      <label htmlFor="description">Description (optional)</label>
      <textarea
        id="description"
        rows={4}
        maxLength={2000}
        value={description}
        onChange={(event) => setDescription(event.target.value)}
      />
      <label htmlFor="tags">Tags (optional, up to 10, separated by commas or spaces)</label>
      <input id="tags" value={tagsInput} onChange={(event) => setTagsInput(event.target.value)} />
      <label className="check" htmlFor="rights">
        <input
          id="rights"
          type="checkbox"
          checked={rights}
          onChange={(event) => setRights(event.target.checked)}
        />
        <span>I confirm I only upload content I own or have the licence to share.</span>
      </label>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button type="submit" disabled={busy}>
        {busy ? "Uploading…" : "Upload"}
      </button>
    </form>
  );
}

export default function UploadPage() {
  return <Gate title="Upload a video">{() => <UploadForm />}</Gate>;
}
