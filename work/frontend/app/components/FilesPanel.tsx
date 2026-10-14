"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { errorText } from "../lib/errors";
import { MAX_DEPTH, MAX_UPLOAD_BYTES, breadcrumbs, formatBytes, joinPath, nameProblem, segments } from "../lib/paths";
import type { Entry, Listing } from "../lib/types";
import { createFolder, deleteEntry, listFiles, renameEntry, uploadFile } from "../lib/workApi";
import EntryItem from "./EntryItem";
import Split from "./Split";
import UploadZone from "./UploadZone";

const WARN_RATIO = 0.9;
const MAX_COLS = 10;

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
  const [cols, setCols] = useState(1);
  const [colsText, setColsText] = useState("1");
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
  const subfolders = entries.filter((e) => e.type === "folder");
  const usage = listing?.usage;
  const ratio = usage && usage.quotaBytes > 0 ? usage.usedBytes / usage.quotaBytes : 0;
  const crumbs = breadcrumbs(path);

  function changeCols(text: string) {
    setColsText(text);
    const value = Math.round(Number(text));
    if (text.trim() !== "" && Number.isFinite(value)) setCols(Math.min(MAX_COLS, Math.max(1, value)));
  }

  const left = (
    <>
      <h3>Folders</h3>
      <nav aria-label="Đường dẫn">
        <ul id="folderTree">
          {crumbs.map((crumb, i) => (
            <li key={crumb.path} style={{ paddingLeft: 10 + i * 12 }}>
              {i === crumbs.length - 1 ? (
                <span aria-current="page">{crumb.label}</span>
              ) : (
                <span role="button" tabIndex={0} className="folder" onClick={() => setPath(crumb.path)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setPath(crumb.path)}>
                  {crumb.label}
                </span>
              )}
            </li>
          ))}
          {subfolders.map((entry) => (
            <li key={entry.name} style={{ paddingLeft: 10 + crumbs.length * 12 }}>
              <span role="button" tabIndex={0} className="folder" onClick={() => setPath(joinPath(path, entry.name))} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setPath(joinPath(path, entry.name))}>
                {`📁 ${entry.name}`}
              </span>
            </li>
          ))}
        </ul>
      </nav>
    </>
  );

  const right = (
    <>
      <h3>Files &amp; Subfolders</h3>
      <div id="currentPath">{`Current Path: ${path}`}</div>
      <div className="rowContainer">
        <label htmlFor="columnCount">Columns:</label>
        <input
          id="columnCount"
          type="number"
          min={1}
          max={MAX_COLS}
          value={colsText}
          onChange={(e) => changeCols(e.target.value)}
          onBlur={() => setColsText(String(cols))}
        />
      </div>
      <form className="rowContainer" onSubmit={submitFolder} aria-label="Tạo thư mục">
        <label htmlFor="folder-name" className="sr-only">
          Tên thư mục mới
        </label>
        <input id="folder-name" placeholder="Tên thư mục mới" value={folderName} maxLength={100} onChange={(e) => setFolderName(e.target.value)} />
        <button type="submit" style={{ flex: "0 0 auto", padding: "0 12px" }}>
          Tạo thư mục
        </button>
      </form>
      <UploadZone busy={busy} onFiles={(files) => void upload(files)} />
      {usage && (
        <div>
          <progress max={usage.quotaBytes} value={usage.usedBytes} aria-label="Dung lượng đã dùng" className="usage" />
          <p className="status-line">
            Đã dùng {formatBytes(usage.usedBytes)} / {formatBytes(usage.quotaBytes)}
          </p>
          {ratio >= WARN_RATIO && (
            <p role="alert" className="text-line">
              Sắp hết dung lượng: đã dùng hơn 90%.
            </p>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="text-line">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-line">
          {notice}
        </p>
      )}
      {!listing && !error && (
        <p className="text-line" role="status">
          Đang tải…
        </p>
      )}
      {listing && entries.length === 0 && <p className="text-line">Thư mục này đang trống.</p>}
      <div className="maxGridContainer" id="fileGridView" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
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
      </div>
    </>
  );

  return (
    <Split
      id="fileSplitter"
      direction="horizontal"
      percent={30}
      containerClass="fullRowContainer"
      firstClass="columnContainer"
      secondClass="columnContainer"
      first={left}
      second={right}
    />
  );
}
