"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { StepList, Status } from "../components";
import { API, MyApplication, errorText, formatDate, label } from "../lib";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import { confirmDialog } from "@sn/compounds/Dialogs";
import Card from "@sn/elements/Card";

export default function ApplicationsList() {
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
        if (!cancelled) setError(errorText(e, tr("could_not_load_your_applications")));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function withdraw(application: MyApplication) {
    if (!(await confirmDialog(tr("withdraw_your_application_to_p0", { p0: application.job_title })))) return;
    setError(null);
    try {
      await apiFetch(`${API}/applications/${application.id}`, { method: "DELETE" });
      setItems((current) => current.filter((item) => item.id !== application.id));
    } catch (e) {
      setError(errorText(e, tr("could_not_withdraw_this_application")));
    }
  }

  return (
    <>
      <Status
        loading={loading}
        error={error}
        empty={items.length === 0}
        emptyText={tr("you_have_not_applied_to_any")}
      />
      {!loading && items.length > 0 && (
        <ul className="list" aria-label={tr("my_applications")}>
          {items.map((item) => (
            <Card stack as="li" key={item.id}>
              <h2 className="break">
                <Link href={`/job/job/${item.job_id}`}>{item.job_title}</Link>
              </h2>
              <p className="muted break" style={{ margin: 0 }}>
                {item.company} {tr("applied_2")} {formatDate(item.created_at)}
              </p>
              <p style={{ margin: 0 }}>
                {tr("status")} <strong>{label(item.status)}</strong>
              </p>
              <StepList steps={item.history} />
              <div className="row">
                {item.status !== "hired" && (
                  <Button variant="secondary" className="secondary" onClick={() => withdraw(item)}>
                    {tr("withdraw")}
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </ul>
      )}
    </>
  );
}

