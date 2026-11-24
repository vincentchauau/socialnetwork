"use client";

import { type CSSProperties, type DragEvent, type ReactNode, useId, useState, useEffect } from "react";
import Button from "../elements/Button";
import { apiForm } from "../api";
import Card from "../elements/Card";
import { BG, FG } from "../lib/theme";
import { crudTr, detailText, type ColumnInfo, type Row, type TableInfo, fileName, fillUrl, mediaKind, mediaSrc, type MediaKind } from "./crudModel";

export interface FileDropZoneProps {
  /** The files that were chosen or dropped and that `accept` allows (only the first one unless `multiple`). */
  onFiles: (files: File[]) => void;
  /** The files that `accept` does not allow, for a line such as "x.exe is not a document" (a picker hides them; a drop does not). */
  onRejected?: (files: File[]) => void;
  /** What may be chosen or dropped, as the `accept` of a file input: any number of extensions and types, ".csv,.pdf,image/*". */
  accept?: string;
  multiple?: boolean;
  /** Something is being sent: nothing more is taken. */
  busy?: boolean;
  disabled?: boolean;
  /** The id of the file input (a label or a test can name it). */
  inputId?: string;
  /** The name of the file input for people who cannot see it. */
  inputLabel?: string;
  testId?: string;
  /**
   * `box`: a big dashed area to drop on or press (its content is `children`, or `prompt` and `hint`).
   * `bar`: a button and a line of words in a dashed bar, to drop on as well.
   * `button`: only the button; there is nothing to drop on.
   */
  variant?: "box" | "bar" | "button";
  /** `box`: what is said in the area, and under it, smaller. */
  prompt?: ReactNode;
  hint?: ReactNode;
  /** `bar` and `button`: the words on the button. */
  buttonLabel?: string;
  /** `bar`: the words after the button. */
  children?: ReactNode;
}

/** Whether `file` is allowed by an `accept` text: its extension, its type, or a family such as `image/*`. */
export function accepts(accept: string | undefined, file: { name: string; type: string }): boolean {
  const wanted = (accept ?? "").split(",").map((part) => part.trim().toLowerCase()).filter(Boolean);
  if (wanted.length === 0) return true;
  const name = file.name.toLowerCase();
  const type = file.type.toLowerCase();
  return wanted.some((part) => (part.startsWith(".") ? name.endsWith(part) : part.endsWith("/*") ? type.startsWith(part.slice(0, -1)) : type === part));
}

const HIDDEN: CSSProperties = { position: "absolute", width: 1, height: 1, padding: 0, margin: -1, overflow: "hidden", clip: "rect(0 0 0 0)", border: 0 };
const BOX: CSSProperties = { display: "block", borderWidth: 2, borderColor: "currentColor", borderRadius: 8, padding: 16, textAlign: "center", cursor: "pointer" };
const BAR: CSSProperties = { display: "flex", alignItems: "center", gap: 8, borderWidth: 1, borderColor: "currentColor", borderRadius: 6, padding: "6px 8px" };

/** Choosing or dropping files, the same in every app: the box of the photos, the bar of the files and the button of the CSV import. */
export default function FileDropZone({ onFiles, onRejected, accept, multiple = false, busy = false, disabled = false, inputId, inputLabel, testId, variant = "box", prompt, hint, buttonLabel = "", children }: FileDropZoneProps) {
  const generated = useId();
  const id = inputId ?? generated;
  const [over, setOver] = useState(false);
  const closed = busy || disabled;

  function take(list: FileList | null) {
    const all = Array.from(list ?? []);
    if (all.length === 0 || closed) return;
    const files = all.filter((file) => accepts(accept, file));
    const refused = all.filter((file) => !files.includes(file));
    if (refused.length > 0) onRejected?.(refused);
    if (files.length > 0) onFiles(multiple ? files : files.slice(0, 1));
  }

  const input = (
    <input
      id={id}
      type="file"
      accept={accept}
      multiple={multiple}
      disabled={closed}
      aria-label={inputLabel}
      {...(variant === "box" ? { style: HIDDEN } : { hidden: true })}
      onChange={(event) => {
        const list = event.target.files;
        take(list);
        event.target.value = ""; // the same file can be chosen again
      }}
    />
  );
  const target = {
    onDragOver: (event: DragEvent) => {
      event.preventDefault();
      if (!closed) setOver(true);
    },
    onDragLeave: () => setOver(false),
    onDrop: (event: DragEvent) => {
      event.preventDefault();
      setOver(false);
      take(event.dataTransfer.files);
    },
  };
  const edge = { borderStyle: over ? "solid" : "dashed" } as const;

  if (variant === "button") {
    return (
      <>
        <Button type="button" size="sm" disabled={closed} onClick={() => document.getElementById(id)?.click()}>
          {buttonLabel}
        </Button>
        {input}
      </>
    );
  }
  if (variant === "bar") {
    return (
      <div data-testid={testId} style={{ ...BAR, ...edge }} {...target}>
        {input}
        <Button type="button" disabled={closed} style={{ flex: "0 0 auto" }} onClick={() => document.getElementById(id)?.click()}>
          {buttonLabel}
        </Button>
        {children && <span>{children}</span>}
      </div>
    );
  }
  return (
    <>
      <label htmlFor={id} data-testid={testId} style={{ ...BOX, ...edge, opacity: closed ? 0.6 : 1 }} {...target}>
        {children ?? (
          <>
            <span>{prompt}</span>
            {hint && (
              <>
                <br />
                <span className="muted">{hint}</span>
              </>
            )}
          </>
        )}
      </label>
      {input}
    </>
  );
}

export interface UploadDialogProps {
  /** Each file is POSTed here as multipart `file`. */
  path: string;
  title: string;
  accept?: string;
  /** Called once all files of a drop were sent (also when some failed). */
  onUploaded: () => void;
  onClose: () => void;
}

type Result = { name: string; error: string | null };

/** The dialog behind a table's `create_via`: drop or choose files, each is sent to `path`. Works for any table. */
export function UploadDialog({ path, title, accept, onUploaded, onClose }: UploadDialogProps) {
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Result[]>([]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function send(files: File[]) {
    setBusy(true);
    const done: Result[] = [];
    for (const file of files) {
      const form = new FormData();
      form.append("file", file);
      try {
        await apiForm(path, form);
        done.push({ name: file.name, error: null });
      } catch (error) {
        done.push({ name: file.name, error: detailText(error) });
      }
      setResults([...done]);
    }
    setBusy(false);
    onUploaded();
  }

  return (
    <div
      data-testid="upload-backdrop"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
      style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", padding: 12, background: "color-mix(in srgb, var(--line, #000) 45%, transparent)" }}
    >
      <div role="dialog" aria-modal="true" aria-label={title} style={{ width: "100%", maxWidth: 520, maxHeight: "90vh", overflow: "auto" }}>
        <Card stack style={{ background: BG, color: FG }}>
          <h3 style={{ margin: 0 }}>{title}</h3>
          <FileDropZone multiple accept={accept} busy={busy} onFiles={send} inputLabel={title} testId="upload-drop" prompt={crudTr("upload_prompt")} />
          {busy ? <small role="status">{crudTr("uploading")}</small> : null}
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {results.map((result, index) => (
              <li key={`${result.name}-${index}`}>{result.name}: {result.error ?? crudTr("upload_done")}</li>
            ))}
          </ul>
          <div><Button type="button" variant="secondary" onClick={onClose}>{crudTr("close")}</Button></div>
        </Card>
      </div>
    </div>
  );
}

export interface MediaFieldProps {
  table: TableInfo;
  column: ColumnInfo;
  row: Row;
  /** Changes after each replacement so the browser fetches the new file. */
  stamp?: number;
  /** Called after a file replaced the current one. */
  onReplaced: () => void;
}

/** The media of a row in its edit dialog: the current file and a drop zone that REPLACES it at once (multipart `file`, PUT to `media.replace`). */
export function MediaField({ table, column, row, stamp, onReplaced }: MediaFieldProps) {
  const media = column.media!;
  const [state, setState] = useState<"idle" | "busy" | "done" | "failed">("idle");
  const [message, setMessage] = useState("");
  const src = mediaSrc(table, column, row, stamp);
  const name = fileName(String(row[column.name] ?? ""));

  async function replace(files: File[]) {
    const form = new FormData();
    form.append("file", files[0]);
    setState("busy");
    try {
      await apiForm(fillUrl(media.replace!, table, row), form, { method: "PUT" });
      setState("done");
      onReplaced();
    } catch (error) {
      setMessage(detailText(error));
      setState("failed");
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }} data-testid={`media-field-${column.name}`}>
      {src ? <div aria-label={crudTr("current_image")}><MediaView kind={mediaKind(media)} src={src} name={name} big /></div> : null}
      <FileDropZone
        accept={media.accept}
        busy={state === "busy"}
        onFiles={replace}
        onRejected={(files) => { setMessage(crudTr("upload_rejected", { names: files.map((file) => file.name).join(", ") })); setState("failed"); }}
        inputLabel={column.name}
        testId={`media-drop-${column.name}`}
        prompt={crudTr("replace_prompt")}
      />
      {state === "busy" ? <small role="status">{crudTr("uploading")}</small> : null}
      {state === "done" ? <small role="status">{crudTr("upload_done")}</small> : null}
      {state === "failed" ? <small role="alert">{message || crudTr("upload_failed")}</small> : null}
    </div>
  );
}

export const BORDER = "1px solid color-mix(in srgb, var(--line) 30%, transparent)";
export const THUMB = { height: 40, width: 40, objectFit: "cover", borderRadius: 4, border: BORDER, verticalAlign: "middle", background: "var(--solid-1, transparent)" } as const;

/** The media element for one kind: a picture, a video or audio player, or a download link. `big`: full size (else a small thumbnail). */
export function MediaView({ kind, src, name, big = false, fill = false }: { kind: MediaKind; src: string; name: string; big?: boolean; fill?: boolean }) {
  if (kind === "image") {
    /* eslint-disable @next/next/no-img-element */
    if (fill && kind === "image") return <img src={src} alt={name} style={{ width: "100%", height: "100%", objectFit: "contain" }} />;
    return big ? <img src={src} alt={name} style={{ maxWidth: "100%", maxHeight: "calc(100vh - 150px)", objectFit: "contain" }} /> : <img src={src} alt={name} loading="lazy" style={THUMB} />;
  }
  if (kind === "video") return <video src={src} controls preload="metadata" style={{ maxWidth: "100%", maxHeight: "70vh" }} aria-label={name} />;
  if (kind === "audio") return <audio src={src} controls preload="none" aria-label={name} style={{ width: "100%" }} />;
  return <a href={src} download={name} target="_blank" rel="noreferrer">{name}</a>;
}

