"use client";

import { FormEvent, useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { Field, Protected, Status } from "../components";
import { API, LIMITS, Profile, errorText, parseTags } from "../lib";

function ProfileEditor() {
  const [headline, setHeadline] = useState("");
  const [skills, setSkills] = useState("");
  const [about, setAbout] = useState("");
  const [openToWork, setOpenToWork] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiFetch<Profile>(`${API}/me/profile`)
      .then((profile) => {
        if (cancelled) return;
        setHeadline(profile.headline);
        setSkills(profile.skills.join(", "));
        setAbout(profile.about);
        setOpenToWork(profile.open_to_work);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(errorText(e, "Could not load your profile"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await apiFetch<Profile>(`${API}/me/profile`, {
        method: "PUT",
        body: JSON.stringify({
          headline,
          skills: parseTags(skills),
          about,
          open_to_work: openToWork,
        }),
      });
      setSaved(true);
    } catch (e) {
      setError(errorText(e, "Could not save your profile"));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Status loading error={null} empty={false} emptyText="" />;

  return (
    <form className="stack card" onSubmit={submit}>
      <p className="muted" style={{ margin: 0 }}>
        Employers only see your profile on jobs you applied to.
      </p>
      <Field label="Headline">
        <input maxLength={LIMITS.headline} value={headline} onChange={(e) => setHeadline(e.target.value)} />
      </Field>
      <Field label={`Skills (comma separated, up to ${LIMITS.skills})`}>
        <input value={skills} onChange={(e) => setSkills(e.target.value)} />
      </Field>
      <Field label="About">
        <textarea rows={6} maxLength={LIMITS.about} value={about} onChange={(e) => setAbout(e.target.value)} />
      </Field>
      <label className="row wrap">
        <input
          type="checkbox"
          checked={openToWork}
          onChange={(e) => setOpenToWork(e.target.checked)}
        />
        <span>Open to work</span>
      </label>
      {error && <p role="alert" className="error">{error}</p>}
      {saved && <p role="status" className="ok">Profile saved.</p>}
      <div className="row">
        <button disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
      </div>
    </form>
  );
}

export default function ProfilePage() {
  return <Protected title="Your profile">{() => <ProfileEditor />}</Protected>;
}
