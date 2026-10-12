"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { apiFetch } from "@sn/api";
import { Protected } from "../../components";
import { API, PostingDetail } from "../../lib";
import { PostingForm, PostingPayload } from "../../posting-form";

function NewPosting() {
  const router = useRouter();

  async function create(payload: PostingPayload) {
    const job = await apiFetch<PostingDetail>(`${API}/jobs`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    router.push(`/employer/${job.id}`);
  }

  return (
    <>
      <Link href="/employer">← My postings</Link>
      <PostingForm submitLabel="Publish job" onSubmit={create} />
    </>
  );
}

export default function NewPostingPage() {
  return <Protected title="Post a job">{() => <NewPosting />}</Protected>;
}
