"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
import BiometricCapture from "./BiometricCapture";
import BiometricWarning from "./BiometricWarning";

interface Props {
  title: string;
  intro: string;
  /** Present for the passwordless option: asks for the username first. */
  askUsername?: boolean;
  submitLabel: string;
  busy: boolean;
  error: string | null;
  showWarning?: boolean;
  onSubmit: (input: { username: string; audio?: Blob; video?: Blob }) => void;
  onCancel: () => void;
}

/** Second-factor / passwordless step: record, submit, or cancel back to the password form. */
export default function BiometricStep(props: Props) {
  const { title, intro, askUsername, submitLabel, busy, error, showWarning, onSubmit, onCancel } = props;
  const [username, setUsername] = useState("");
  const [audio, setAudio] = useState<Blob>();
  const [video, setVideo] = useState<Blob>();

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit({ username, audio, video });
  }

  return (
    <form className="stack" onSubmit={submit} aria-label={title}>
      <h1>{title}</h1>
      <p className="muted">{intro}</p>
      {showWarning && <BiometricWarning />}
      {askUsername && (
        <label className="stack" style={{ gap: 4 }}>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
        </label>
      )}
      <BiometricCapture disabled={busy} onVideo={setVideo} onAudio={setAudio} />
      <Alert text={error} />
      <button disabled={busy || (!audio && !video)}>{busy ? "Checking…" : submitLabel}</button>
      <button type="button" className="secondary" onClick={onCancel} disabled={busy}>
        Cancel
      </button>
    </form>
  );
}
