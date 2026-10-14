"use client";

import { DragEvent, useRef, useState } from "react";

interface Props {
  busy: boolean;
  onFiles: (files: File[]) => void;
}

/** Upload button plus drag and drop target. The shared client has no progress events, so only a busy state is shown. */
export default function UploadZone({ busy, onFiles }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  function drop(event: DragEvent) {
    event.preventDefault();
    setOver(false);
    const files = Array.from(event.dataTransfer.files);
    if (files.length > 0) onFiles(files);
  }

  return (
    <div
      className={over ? "dropzone over" : "dropzone"}
      data-testid="dropzone"
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
    >
      <input
        ref={inputRef}
        id="work-upload"
        type="file"
        multiple
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length > 0) onFiles(files);
        }}
      />
      <button type="button" disabled={busy} onClick={() => inputRef.current?.click()}>
        {busy ? "Đang tải lên…" : "Tải tệp lên"}
      </button>
      <span className="muted"> hoặc kéo thả tệp vào đây (tối đa 20 MB mỗi tệp)</span>
    </div>
  );
}
