"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { errorText } from "../lib/errors";
import { MAX_DEPTH, MAX_UPLOAD_BYTES, breadcrumbs, formatBytes, joinPath, nameProblem, segments } from "../lib/paths";
import type { Entry, Listing } from "../lib/types";
import { createFolder, deleteEntry, listFiles, renameEntry, uploadFile } from "../lib/workApi";
import EntryItem from "./EntryItem";
import UploadZone from "./UploadZone";

const WARN_RATIO = 0.9;

function sortEntries(entries: Entry[]): Entry[] {
  return [...entries].sort((a, b) =>
    a.type === b.type ? a.name.localeCompare(b.name, "vi") : a.type === "folder" ? -1 : 1,
  );
}

export default function FilesPanel() {
  const [path, setPath] = useState("/");
  const [listing, setListing] = useState<Listing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cols, setCols] = useState(3);
  const [layout, setLayout] = useState<"grid" | "list">("grid");
  const [folderName, setFolderName] = useState("");

  const load = useCallback(async (target: string) => {
    try {
      setListing(await listFiles(target));
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, []);

  useEffect(() => {
    void load(path);
  }, [load, path]);

  async function run(action: () => Promise<unknown>, done?: string) {
    setNotice(null);
    try {
      await action();
      setError(null);
      if (done) setNotice(done);
      await load(path);
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function submitFolder(event: FormEvent) {
    event.preventDefault();
    const problem = nameProblem(folderName);
    if (problem) return setError(problem);
    if (segments(path).length >= MAX_DEPTH) return setError(`Thư mục lồng nhau tối đa ${MAX_DEPTH} cấp.`);
    await run(() => createFolder(path, folderName), "Đã tạo thư mục.");
    setFolderName("");
  }

  async function upload(files: File[]) {
    setBusy(true);
    setNotice(null);
    let remaining = listing ? listing.usage.quotaBytes - listing.usage.usedBytes : Infinity;
    const problems: string[] = [];
    let uploaded = 0;
    for (const file of files) {
      if (file.size > MAX_UPLOAD_BYTES) {
        problems.push(`${file.name}: tệp lớn hơn 20 MB.`);
      } else if (file.size > remaining) {
        problems.push(`${file.name}: không đủ dung lượng còn lại (${formatBytes(Math.max(remaining, 0))}).`);
      } else {
        try {
          await uploadFile(path, file);
          remaining -= file.size;
          uploaded += 1;
        } catch (e) {
          problems.push(`${file.name}: ${errorText(e)}`);
        }
      }
    }
    await load(path);
    setError(problems.length > 0 ? problems.join(" ") : null);
    if (uploaded > 0) setNotice(`Đã tải lên ${uploaded} tệp.`);
    setBusy(false);
  }

  const entries = listing ? sortEntries(listing.entries) : [];
  const usage = listing?.usage;
  const ratio = usage && usage.quotaBytes > 0 ? usage.usedBytes / usage.quotaBytes : 0;
  const gridStyle = layout === "grid" ? { gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` } : undefined;

  return (
    <div className="stack">
      <nav aria-label="Đường dẫn">
        <ol className="crumbs">
          {breadcrumbs(path).map((crumb, i, all) => (
            <li key={crumb.path}>
              {i === all.length - 1 ? (
                <span aria-current="page">{crumb.label}</span>
              ) : (
                <button type="button" className="link" onClick={() => setPath(crumb.path)}>
                  {crumb.label}
                </button>
              )}
            </li>
          ))}
        </ol>
      </nav>

      {usage && (
        <div>
          <progress
            max={usage.quotaBytes}
            value={usage.usedBytes}
            aria-label="Dung lượng đã dùng"
            className={ratio >= WARN_RATIO ? "usage warn" : "usage"}
          />
          <p className="muted">
            Đã dùng {formatBytes(usage.usedBytes)} / {formatBytes(usage.quotaBytes)}
          </p>
          {ratio >= WARN_RATIO && (
            <p role="alert" className="error">
              Sắp hết dung lượng: đã dùng hơn 90%.
            </p>
          )}
        </div>
      )}

      <form className="row" onSubmit={submitFolder} aria-label="Tạo thư mục">
        <label htmlFor="folder-name" className="sr-only">
          Tên thư mục mới
        </label>
        <input
          id="folder-name"
          placeholder="Tên thư mục mới"
          value={folderName}
          maxLength={100}
          onChange={(e) => setFolderName(e.target.value)}
        />
        <button type="submit">Tạo thư mục</button>
      </form>

      <UploadZone busy={busy} onFiles={(files) => void upload(files)} />

      <div className="row toolbar">
        <button
          type="button"
          className="secondary"
          aria-pressed={layout === "grid"}
          onClick={() => setLayout(layout === "grid" ? "list" : "grid")}
        >
          {layout === "grid" ? "Chuyển sang danh sách" : "Chuyển sang lưới"}
        </button>
        {layout === "grid" && (
          <label className="cols">
            Số cột{" "}
            <input
              type="number"
              min={1}
              max={6}
              value={cols}
              onChange={(e) => setCols(Math.min(6, Math.max(1, Number(e.target.value) || 1)))}
            />
          </label>
        )}
      </div>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}

      {!listing && !error && (
        <p className="muted" role="status">
          Đang tải…
        </p>
      )}
      {listing && entries.length === 0 && <p className="muted">Thư mục này đang trống.</p>}
      {entries.length > 0 && (
        <ul className={layout === "grid" ? "entries grid" : "entries list"} style={gridStyle}>
          {entries.map((entry) => (
            <EntryItem
              key={`${entry.type}:${entry.name}`}
              entry={entry}
              dir={path}
              onOpen={(name) => setPath(joinPath(path, name))}
              onRename={(e, newName) => run(() => renameEntry(joinPath(path, e.name), newName), "Đã đổi tên.")}
              onDelete={(e) => run(() => deleteEntry(joinPath(path, e.name)), "Đã xoá.")}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
