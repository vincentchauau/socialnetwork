"use client";

import { useParams } from "next/navigation";

import { ResourceView, Shell, useResource } from "../../lib";

interface PublicCertificate {
  learner: string;
  course: string;
  completed_at: string;
}

export default function VerifyCertificatePage() {
  const { code } = useParams<{ code: string }>();
  const [state] = useResource<PublicCertificate>(`/certificates/${encodeURIComponent(code)}`);
  return (
    <Shell title="Verify certificate">
      <ResourceView state={state}>
        {(cert) => (
          <section className="card stack" aria-label="Valid certificate">
            <p className="ok" role="status">
              This certificate is valid.
            </p>
            <p>
              <strong>{cert.learner}</strong> completed <strong>{cert.course}</strong> on{" "}
              {new Date(cert.completed_at).toLocaleDateString()}.
            </p>
          </section>
        )}
      </ResourceView>
    </Shell>
  );
}
