"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { apiFetch } from "@sn/api";

import { API, formatBytes } from "../../lib/paths";
import { tr } from "../../i18n";

interface Shared {
  name: string;
  size: number;
  modifiedAt: number;
  download: string;
}

/** A file that its owner gave by a link: anybody who has the link sees its name and size and may download it (no sign-in). */
export default function SharedFilePage() {
  const { token } = useParams<{ token: string }>();
  const [file, setFile] = useState<Shared | null | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    apiFetch<Shared>(`${API}/shared/${encodeURIComponent(token)}`).then(
      (found) => !cancelled && setFile(found),
      () => !cancelled && setFile(null),
    );
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (file === undefined) return <p role="status" className="muted">{tr("dang_tai")}</p>;
  if (file === null) return <p role="alert" className="error">{tr("share_link_gone")}</p>;
  return (
    <main className="stack" style={{ alignItems: "center", textAlign: "center" }}>
      <h1 style={{ overflowWrap: "anywhere" }}>📄 {file.name}</h1>
      <p className="muted" style={{ margin: 0 }}>{formatBytes(file.size)} · {new Date(file.modifiedAt * 1000).toLocaleDateString()}</p>
      <a href={`${API}${file.download}`} download={file.name} className="button">⬇ {tr("fl_tai_xuong")}</a>
    </main>
  );
}
