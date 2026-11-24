"use client";

import { useCallback, useEffect, useState } from "react";

import { httpErrorText as errorText } from "@sn/api";
import Button from "@sn/elements/Button";
import { intlLocale } from "@sn/lib/i18n";

import { dropVersion, listVersions, restoreVersion } from "../lib/api";
import { formatBytes } from "../lib/paths";
import type { VersionEntry } from "../lib/types";
import { tr } from "../i18n";

const when = (seconds: number): string => new Date(seconds * 1000).toLocaleString(intlLocale(), { dateStyle: "short", timeStyle: "short" });

/** The earlier versions of one file (what it was before it was replaced): each can be put back, which keeps what the file is now as a version. */
export default function VersionsSection({ path, name, onRestored, onClose }: { path: string; name: string; onRestored: () => void; onClose: () => void }) {
  const [found, setFound] = useState<VersionEntry[] | null>(null);
  const [keepDays, setKeepDays] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const answer = await listVersions(path);
      setFound(answer.versions);
      setKeepDays(answer.keepDays);
    } catch (failure) {
      setFound([]);
      setError(errorText(failure));
    }
  }, [path]);

  useEffect(() => {
    setNotice(null);
    setError(null);
    void load();
  }, [load]);

  async function restore(version: VersionEntry) {
    setError(null);
    try {
      await restoreVersion(version.id);
      setNotice(tr("versions_restored_p0", { p0: name }));
      onRestored();
    } catch (failure) {
      setError(errorText(failure));
    }
    await load();
  }

  async function drop(version: VersionEntry) {
    setError(null);
    try {
      await dropVersion(version.id);
    } catch (failure) {
      setError(errorText(failure));
    }
    await load();
  }

  return (
    <section aria-label={tr("versions_of_p0", { p0: name })} className="stack" style={{ gap: 6 }}>
      <div className="row" style={{ alignItems: "center", gap: 8 }}>
        <strong>🕘 {tr("versions_of_p0", { p0: name })}</strong>
        <span style={{ flex: 1 }} />
        <Button type="button" size="sm" variant="ghost" aria-label={tr("huy")} onClick={onClose}>✕</Button>
      </div>
      <p className="muted" style={{ margin: 0 }}>{tr("versions_hint_p0", { p0: keepDays })}</p>
      {found === null ? <p role="status" className="muted" style={{ margin: 0 }}>…</p> : null}
      {found !== null && found.length === 0 ? <p className="muted" style={{ margin: 0 }}>{tr("versions_none")}</p> : null}
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
        {(found ?? []).map((version) => (
          <li key={version.id} className="row" style={{ alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ flex: "1 1 160px" }}>{when(version.savedAt)} · {formatBytes(version.size)}</span>
            <Button type="button" size="sm" onClick={() => void restore(version)}>{tr("trash_restore")}</Button>
            <Button type="button" size="sm" variant="secondary" onClick={() => void drop(version)}>{tr("trash_erase")}</Button>
          </li>
        ))}
      </ul>
      {notice ? <p role="status" style={{ margin: 0 }}>{notice}</p> : null}
      {error ? <p role="alert" className="error" style={{ margin: 0 }}>{error}</p> : null}
    </section>
  );
}
