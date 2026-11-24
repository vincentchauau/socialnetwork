"use client";

import { FormEvent, useState } from "react";

import { httpErrorText as errorText } from "@sn/api";
import Button from "@sn/elements/Button";
import TextBox from "@sn/elements/TextBox";

import { searchFiles } from "../lib/api";
import { formatBytes, joinPath } from "../lib/paths";
import type { FoundEntry } from "../lib/types";
import { tr } from "../i18n";

const MIN_LETTERS = 2;

/** Looks for a file or a folder by its name in every folder; a result opens the folder it is in. */
export default function SearchPanel({ onOpen }: { onOpen: (folder: string) => void }) {
  const [words, setWords] = useState("");
  const [found, setFound] = useState<{ entries: FoundEntry[]; more: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function look(event: FormEvent) {
    event.preventDefault();
    if (busy || words.trim().length < MIN_LETTERS) return;
    setBusy(true);
    setError(null);
    try {
      setFound(await searchFiles(words.trim()));
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label={tr("search_files")} className="stack" style={{ padding: 8 }}>
      <form onSubmit={look} role="search" className="row" style={{ gap: 8, alignItems: "center" }}>
        <TextBox type="search" aria-label={tr("search_files")} placeholder={tr("search_in_all_folders")} value={words} maxLength={100} onChange={(event) => setWords(event.target.value)} />
      </form>
      {error ? <p role="alert" className="error" style={{ margin: 0 }}>{error}</p> : null}
      {found && found.entries.length === 0 ? <p className="muted" style={{ margin: 0 }}>{tr("search_nothing")}</p> : null}
      {found && found.entries.length > 0 ? (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
          {found.entries.map((entry) => {
            const folder = entry.type === "folder" ? joinPath(entry.parent, entry.name) : entry.parent;
            return (
              <li key={`${entry.parent}/${entry.name}`}>
                <Button type="button" size="sm" variant="ghost" style={{ textAlign: "left", maxWidth: "100%" }} onClick={() => onOpen(folder)}>
                  {entry.type === "folder" ? "📁" : "📄"} {entry.name} <span className="muted">· {entry.parent}{entry.type === "file" ? ` · ${formatBytes(entry.size)}` : ""}</span>
                </Button>
              </li>
            );
          })}
        </ul>
      ) : null}
      {found?.more ? <p className="muted" style={{ margin: 0 }}>{tr("search_more")}</p> : null}
    </section>
  );
}
