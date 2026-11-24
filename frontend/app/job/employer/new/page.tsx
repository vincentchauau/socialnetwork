"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { apiFetch } from "@sn/api";
import { notifyRecordsChanged } from "@sn/lib/recordsChanged";
import { Protected } from "../../components";
import { API, JobDescriptionDetail } from "../../lib";
import { JobDescriptionForm, JobDescriptionPayload } from "../../job-description-form";
import { tr } from "../../i18n";

function NewPosting() {
  const router = useRouter();

  async function create(payload: JobDescriptionPayload) {
    const job = await apiFetch<JobDescriptionDetail>(`${API}/jobs`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    notifyRecordsChanged("job_descriptions");
    router.push(`/job/employer/${job.id}`);
  }

  return (
    <>
      <Link href="/job/employer">{tr("my_postings_2")}</Link>
      <JobDescriptionForm submitLabel={tr("publish_job")} onSubmit={create} />
    </>
  );
}

export default function NewJobDescriptionPage() {
  return <Protected title={tr("post_a_job")}>{() => <NewPosting />}</Protected>;
}
