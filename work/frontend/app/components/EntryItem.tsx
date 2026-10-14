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

/** One grid tile (preview + name) like the original ChatWork file explorer. Names are plain text. */
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
    <div className="grid-item">
      <div className="file-preview" style={{ background: "inherit", aspectRatio: "auto", height: 90 }}>
        {isFolder ? (
          <span
            role="button"
            tabIndex={0}
            className="emoji folder"
            aria-label={`Mở thư mục ${entry.name}`}
            onClick={() => onOpen(entry.name)}
            onKeyDown={(event) => (event.key === "Enter" || event.key === " ") && onOpen(entry.name)}
          >
            📁
          </span>
        ) : (
          <a href={downloadUrl(joinPath(dir, entry.name))} download={entry.name} aria-label={`Tải xuống ${entry.name}`}>
            <span className="emoji">📄</span>
          </a>
        )}
      </div>
      <div className="file-name">{entry.name}</div>
      <div className="text-line" style={{ fontSize: "0.8em" }}>
        {isFolder ? "Thư mục" : formatBytes(entry.size)} · {entry.modifiedAt}
      </div>
      {mode === "view" && (
        <div className="rowContainer" style={{ width: "100%" }}>
          <button type="button" aria-label={`Đổi tên ${entry.name}`} onClick={() => setMode("rename")}>
            Đổi tên
          </button>
          <button type="button" aria-label={`Xoá ${entry.name}`} onClick={() => setMode("delete")}>
            Xoá
          </button>
        </div>
      )}
      {mode === "rename" && (
        <form className="columnContainer" style={{ width: "100%" }} onSubmit={submitRename} aria-label={`Đổi tên ${entry.name}`}>
          <label htmlFor={`rename-${entry.name}`}>Tên mới</label>
          <input id={`rename-${entry.name}`} value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
          {problem && (
            <p role="alert" className="text-line">
              {problem}
            </p>
          )}
          <div className="rowContainer">
            <button type="submit">Lưu</button>
            <button type="button" onClick={() => setMode("view")}>
              Huỷ
            </button>
          </div>
        </form>
      )}
      {mode === "delete" && (
        <div className="columnContainer" style={{ width: "100%" }} role="group" aria-label="Xác nhận xoá">
          <p className="text-line">
            Xoá <strong>{entry.name}</strong>
            {isFolder ? " và toàn bộ nội dung bên trong" : ""}?
          </p>
          <div className="rowContainer">
            <button type="button" onClick={confirmDelete}>
              Xác nhận xoá
            </button>
            <button type="button" onClick={() => setMode("view")}>
              Huỷ
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
