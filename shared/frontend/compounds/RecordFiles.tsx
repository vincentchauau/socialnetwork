"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "../api";
import type { ColumnInfo } from "./crudModel";

/** The width of each kind of file in a cell: the same for every file of one kind, so the cells line up. */
const MEDIA_WIDTH = { image: 96, audio: 200, video: 128, file: 160 } as const;

interface CellFile {
  name: string;
  kind: "image" | "audio" | "video" | "file";
}

/** The first file of a picture, audio, video or file cell of a row, shown as what it is (no text). */
/** Every file of the cell, in a row that scrolls sideways; `all` adds a × to each one to remove it (the record dialog). */
export default function CellFiles({ api, table, pk, column, all, onError }: {
  api: string; table: string; pk: string; column: string; all?: boolean; onError?: (message: string) => void;
}) {
  const [files, setFiles] = useState<CellFile[]>([]);
  const [version, setVersion] = useState(0);
  const base = `${api}/${encodeURIComponent(table)}/${pk}/files/${encodeURIComponent(column)}`;

  useEffect(() => {
    let alive = true;
    apiFetch<{ files: CellFile[] }>(base)
      .then((response) => { if (alive) setFiles(Array.isArray(response?.files) ? response.files : []); })
      .catch(() => { if (alive) setFiles([]); });
    return () => { alive = false; };
  }, [base, version]);

  const remove = async (name: string) => {
    try {
      await apiFetch(`${base}/${encodeURIComponent(name)}`, { method: "DELETE" });
      setVersion((value) => value + 1);
    } catch (failure) {
      onError?.(failure instanceof Error ? failure.message : "The file could not be removed.");
    }
  };

  if (files.length === 0) return null;
  return (
    <div style={{ display: "flex", flexWrap: all ? "wrap" : "nowrap", alignItems: "flex-start", gap: 10, padding: 4, overflowX: all ? undefined : "auto", maxWidth: all ? undefined : 520 }}>
      {files.map((file) => {
        const src = `${base}/${encodeURIComponent(file.name)}`;
        return (
          <div key={file.name} title={file.name} style={{ position: "relative", width: MEDIA_WIDTH[file.kind], display: "grid", gap: 4, justifyItems: "stretch", pointerEvents: "auto" }}>
            {all ? <button type="button" aria-label={`Remove ${file.name}`} onClick={() => void remove(file.name)} style={{ position: "absolute", top: file.kind === "audio" ? -8 : 4, right: file.kind === "audio" ? -8 : 4, zIndex: 2, width: 22, height: 22, borderRadius: 999, border: "1px solid rgba(255,255,255,0.7)", background: "color-mix(in srgb, var(--line) 75%, transparent)", color: "var(--solid-0)", cursor: "pointer", lineHeight: "20px", padding: 0, fontSize: 14 }}>×</button> : null}
            {file.kind === "image" ? <img src={src} alt={file.name} loading="lazy" style={{ width: MEDIA_WIDTH.image, height: 72, objectFit: "cover", borderRadius: 6, display: "block" }} /> : null}
            {file.kind === "audio" ? <audio controls preload="metadata" src={src} onClick={(event) => event.stopPropagation()} style={{ width: MEDIA_WIDTH.audio, height: 36, display: "block", marginTop: 6 }} /> : null}
            {file.kind === "video" ? <video controls preload="metadata" src={src} onClick={(event) => event.stopPropagation()} style={{ width: MEDIA_WIDTH.video, height: 72, objectFit: "contain", background: "var(--line)", borderRadius: 6, display: "block" }} /> : null}
            {file.kind === "file" ? <a href={src} style={{ fontSize: 12 }}>{file.name}</a> : null}
          </div>
        );
      })}
    </div>
  );
}


