"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import Alert from "@sn/elements/Alert";
import Button from "@sn/elements/Button";
import TextBox from "@sn/elements/TextBox";
import { API, LIMITS, MyApplication, errorText } from "./lib";
import { tr } from "./i18n";

/** The applications the employer has not reviewed yet: the person changes the cover letter and the contact email of each. */
export default function PendingApplications() {
  const [applications, setApplications] = useState<MyApplication[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    apiFetch<MyApplication[]>(`${API}/me/applications`)
      .then((list) => {
        if (alive) setApplications(list.filter((application) => application.status === "submitted"));
      })
      .catch((failure: unknown) => {
        if (alive) setError(errorText(failure));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (loading) return <p role="status" className="muted">{tr("loading")}</p>;
  if (error) return <Alert tone="error">{error}</Alert>;
  if (applications.length === 0) return <p className="muted">{tr("no_pending_applications")}</p>;
  return (
    <ul className="list" aria-label={tr("update_applications")}>
      {applications.map((application) => (
        <PendingCard
          key={application.id}
          application={application}
          onSaved={(updated) => setApplications((current) => current.map((item) => (item.id === updated.id ? updated : item)))}
        />
      ))}
    </ul>
  );
}

function PendingCard({ application, onSaved }: { application: MyApplication; onSaved: (updated: MyApplication) => void }) {
  const [cover, setCover] = useState(application.cover_letter);
  const [contact, setContact] = useState(application.contact_email ?? "");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  async function save() {
    setBusy(true);
    setProblem("");
    try {
      const updated = await apiFetch<MyApplication>(`${API}/applications/${application.id}/mine`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cover_letter: cover, contact_email: contact.trim() || null }),
      });
      onSaved(updated);
    } catch (failure) {
      setProblem(errorText(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="stack">
      <strong>{application.job_title}</strong>
      <span className="muted">{application.company}</span>
      <TextBox multiline maxLength={LIMITS.coverLetter} aria-label={tr("cover_letter")} value={cover} onChange={(event) => setCover(event.target.value)} />
      <TextBox type="email" aria-label={tr("contact_email")} placeholder={tr("contact_email")} value={contact} onChange={(event) => setContact(event.target.value)} />
      {problem ? <Alert tone="error">{problem}</Alert> : null}
      <div>
        <Button type="button" size="sm" loading={busy} onClick={() => void save()}>{tr("save_changes")}</Button>
      </div>
    </li>
  );
}
