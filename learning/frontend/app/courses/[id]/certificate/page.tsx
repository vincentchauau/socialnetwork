"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { RequireAuth, ResourceView, Shell, useAuth, useResource } from "../../../lib";

interface Certificate {
  learner: string;
  course: string;
  completed_at: string;
  code: string;
}

export default function CertificatePage() {
  const { id } = useParams<{ id: string }>();
  const auth = useAuth();
  const [state] = useResource<Certificate>(
    auth.status === "signed-in" ? `/courses/${id}/certificate` : null,
  );
  return (
    <Shell title="Certificate">
      <p>
        <Link href={`/courses/${id}`}>← Back to course</Link>
      </p>
      <RequireAuth auth={auth}>
        {() => (
          <ResourceView state={state}>
            {(cert) => (
              <section className="card stack" aria-label="Certificate of completion">
                <h2>Certificate of completion</h2>
                <p>
                  <strong>{cert.learner}</strong> completed <strong>{cert.course}</strong> on{" "}
                  {new Date(cert.completed_at).toLocaleDateString()}.
                </p>
                <p className="muted">Verification code</p>
                <p className="prewrap">
                  <code>{cert.code}</code>
                </p>
                <p>
                  <Link href={`/certificates/${cert.code}`}>Public verification page</Link>
                </p>
              </section>
            )}
          </ResourceView>
        )}
      </RequireAuth>
    </Shell>
  );
}
