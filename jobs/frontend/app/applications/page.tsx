"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { Protected, Status } from "../components";
import { API, MyApplication, errorText, formatDate, label } from "../lib";

function Applications() {
  const [items, setItems] = useState<MyApplication[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<MyApplication[]>(`${API}/me/applications`)
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(errorText(e, "Could not load your applications"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function withdraw(application: MyApplication) {
    if (!window.confirm(`Withdraw your application to ${application.job_title}?`)) return;
    setError(null);
    try {
      await apiFetch(`${API}/applications/${application.id}`, { method: "DELETE" });
      setItems((current) => current.filter((item) => item.id !== application.id));
    } catch (e) {
      setError(errorText(e, "Could not withdraw this application"));
    }
  }

  return (
    <>
      <Status
        loading={loading}
        error={error}
        empty={items.length === 0}
        emptyText="You have not applied to any jobs yet."
      />
      {!loading && items.length > 0 && (
        <ul className="list" aria-label="My applications">
          {items.map((item) => (
            <li key={item.id} className="card stack">
              <h2 className="break">
                <Link href={`/job/${item.job_id}`}>{item.job_title}</Link>
              </h2>
              <p className="muted break" style={{ margin: 0 }}>
                {item.company} · Applied {formatDate(item.created_at)}
              </p>
              <p style={{ margin: 0 }}>
                Status: <strong>{label(item.status)}</strong>
              </p>
              <div className="row">
                {item.status !== "hired" && (
                  <button className="secondary" onClick={() => withdraw(item)}>
                    Withdraw
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export default function ApplicationsPage() {
  return <Protected title="My applications">{() => <Applications />}</Protected>;
}
