"use client";

import { FormEvent, useRef, useState } from "react";

import { ACCEPTED_TYPES, MAX_TEXT_CHARS, Photo, errorText, uploadPhoto, validateFile } from "./photos";

export function UploadForm({ onUploaded }: { onUploaded: (photo: Photo) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [caption, setCaption] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const file = fileRef.current?.files?.[0] ?? null;
    const problem = validateFile(file);
    if (problem || !file) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onUploaded(await uploadPhoto(file, caption));
      setCaption("");
      if (fileRef.current) fileRef.current.value = "";
    } catch (e) {
      setError(errorText(e, "Upload failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card stack" onSubmit={submit} aria-label="Upload a photo">
      <label htmlFor="photo-file">Photo (JPEG, PNG, WebP or GIF, max 5 MB)</label>
      <input id="photo-file" ref={fileRef} type="file" accept={ACCEPTED_TYPES.join(",")} required />
      <label htmlFor="photo-caption">Caption (optional)</label>
      <input
        id="photo-caption"
        value={caption}
        maxLength={MAX_TEXT_CHARS}
        onChange={(event) => setCaption(event.target.value)}
      />
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button type="submit" disabled={busy}>
        {busy ? "Uploading…" : "Upload"}
      </button>
    </form>
  );
}
