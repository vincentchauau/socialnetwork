"use client";

import { FormEvent, useState } from "react";

import type { Entry } from "../lib/types";
import { downloadUrl, formatBytes, joinPath, nameProblem } from "../lib/paths";

interface Props {
  entry: Entry;
  dir: string;
  onOpen: (name: string) => void;
  onRename: (entry: Entry, newName: string) => Promise<void>;
  onDelete: (entry: Entry) => Promise<void>;
}

type Mode = "view" | "rename" | "delete";

/** One file or folder. Names are always rendered as plain text. */
export default function EntryItem({ entry, dir, onOpen, onRename, onDelete }: Props) {
  const [mode, setMode] = useState<Mode>("view");
  const [name, setName] = useState(entry.name);
  const [problem, setProblem] = useState<string | null>(null);
  const isFolder = entry.type === "folder";

  async function submitRename(event: FormEvent) {
    event.preventDefault();
    const found = nameProblem(name);
    if (found) {
      setProblem(found);
      return;
    }
    setProblem(null);
    await onRename(entry, name);
    setMode("view");
  }

  async function confirmDelete() {
    await onDelete(entry);
    setMode("view");
  }

  return (
    <li className="card entry">
      <div className="entry-title">
        <span aria-hidden="true">{isFolder ? "📁" : "📄"}</span>{" "}
        {isFolder ? (
          <button type="button" className="link" onClick={() => onOpen(entry.name)}>
            {entry.name}
          </button>
        ) : (
          <span className="entry-name">{entry.name}</span>
        )}
        <span className="muted entry-meta">
          {isFolder ? "Thư mục" : formatBytes(entry.size)} · {entry.modifiedAt}
        </span>
      </div>
      {mode === "view" && (
        <div className="row entry-actions">
          {!isFolder && (
            <a
              className="btn secondary"
              href={downloadUrl(joinPath(dir, entry.name))}
              download={entry.name}
              aria-label={`Tải xuống ${entry.name}`}
            >
              Tải xuống
            </a>
          )}
          <button type="button" className="secondary" aria-label={`Đổi tên ${entry.name}`} onClick={() => setMode("rename")}>
            Đổi tên
          </button>
          <button type="button" className="secondary" aria-label={`Xoá ${entry.name}`} onClick={() => setMode("delete")}>
            Xoá
          </button>
        </div>
      )}
      {mode === "rename" && (
        <form className="stack" onSubmit={submitRename} aria-label={`Đổi tên ${entry.name}`}>
          <label htmlFor={`rename-${entry.name}`}>Tên mới</label>
          <input id={`rename-${entry.name}`} value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
          {problem && (
            <p role="alert" className="error">
              {problem}
            </p>
          )}
          <div className="row">
            <button type="submit">Lưu</button>
            <button type="button" className="secondary" onClick={() => setMode("view")}>
              Huỷ
            </button>
          </div>
        </form>
      )}
      {mode === "delete" && (
        <div className="stack" role="group" aria-label="Xác nhận xoá">
          <p>
            Xoá <strong>{entry.name}</strong>
            {isFolder ? " và toàn bộ nội dung bên trong" : ""}?
          </p>
          <div className="row">
            <button type="button" className="danger" onClick={confirmDelete}>
              Xác nhận xoá
            </button>
            <button type="button" className="secondary" onClick={() => setMode("view")}>
              Huỷ
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
