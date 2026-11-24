"use client";

import { type ChangeEvent, type KeyboardEvent as ReactKeyboardEvent, type ReactNode, useEffect, useId, useState } from "react";
import Button from "../elements/Button";
import Card from "../elements/Card";
import { BG, FG } from "../lib/theme";
import { useT } from "../locales";
import type { MediaKind } from "./crudModel";

export interface ConfirmModalProps {
  open: boolean;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmLabel?: string;
  cancelLabel?: string;
}

/** Confirmation dialog for destructive actions. Escape or a click on the backdrop cancels; Cancel has focus first. */
export function ConfirmModal({ open, message, onConfirm, onCancel, confirmLabel = "Delete", cancelLabel = "Cancel" }: ConfirmModalProps) {
  const messageId = useId();

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div
      data-testid="confirm-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
      style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", background: "color-mix(in srgb, var(--line, #000) 45%, transparent)" }}
    >
      <Card
        stack
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={messageId}
        style={{ width: "100%", maxWidth: 320, alignItems: "center", background: BG, color: FG }}
      >
        <div id={messageId} style={{ fontWeight: 600, textAlign: "center" }}>
          {message}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button variant="danger" onClick={onConfirm}>
            {confirmLabel}
          </Button>
          <Button variant="secondary" onClick={onCancel} autoFocus>
            {cancelLabel}
          </Button>
        </div>
      </Card>
    </div>
  );
}

export default ConfirmModal;

interface Ask {
  message: string;
  answer: (yes: boolean) => void;
}

let show: ((ask: Ask) => void) | null = null;

/**
 * Asks a yes / no question in the dialog of the site and answers with the choice; `await confirmDialog("Delete it?")`. Needs
 * <ConfirmHost /> somewhere on the page (the root layout has it); without one it falls back to the dialog of the browser.
 */
export function confirmDialog(message: string): Promise<boolean> {
  if (show === null) return Promise.resolve(typeof window !== "undefined" ? window.confirm(message) : false);
  const open = show;
  return new Promise((resolve) => open({ message, answer: resolve }));
}

export function ConfirmHost() {
  const { t } = useT();
  const [ask, setAsk] = useState<Ask | null>(null);

  useEffect(() => {
    show = setAsk;
    return () => {
      show = null;
    };
  }, []);

  const close = (yes: boolean) => {
    ask?.answer(yes);
    setAsk(null);
  };
  return (
    <ConfirmModal
      open={ask !== null}
      message={ask?.message ?? ""}
      confirmLabel={t("confirm.yes")}
      cancelLabel={t("confirm.no")}
      onConfirm={() => close(true)}
      onCancel={() => close(false)}
    />
  );
}

/** The largest file a picture, audio, video or other file cell takes (a cell keeps the file inside the row). */
const CELL_FILE_LIMIT: Record<MediaKind, number> = {
  image: 2 * 1024 * 1024,
  audio: 3 * 1024 * 1024,
  video: 15 * 1024 * 1024,
  file: 5 * 1024 * 1024,
};

/** The file types the dialog offers when the column says none. */
const DEFAULT_ACCEPT: Record<MediaKind, string> = { image: "image/*", audio: "audio/*", video: "video/*", file: "*/*" };

/** What a file cell shows instead of its data: the kind of file and its size, never the bytes. */
export function fileCellText(value: string): string {
  if (!value.startsWith("data:")) return value;
  const [head, body = ""] = value.split(",", 2);
  const bytes = Math.floor((body.length * 3) / 4);
  return `${head.slice(5).split(";")[0]} · ${(bytes / 1024).toFixed(0)} KB`;
}

export function Dialog({ label, onClose, children }: { label: string; onClose: () => void; children: ReactNode }) {
  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") onClose();
  };
  return (
    <div role="dialog" aria-modal="true" aria-label={label} onKeyDown={onKeyDown} style={{ position: "fixed", inset: 0, display: "grid", placeItems: "center", background: "color-mix(in srgb, var(--line) 45%, transparent)", zIndex: 50 }}>
      <div style={{ background: "var(--surface, #2a1a1a)", color: "inherit", padding: 16, borderRadius: 8, minWidth: 320, maxWidth: 520, display: "grid", gap: 10 }}>
        <strong>{label}</strong>
        {children}
        <div><button type="button" onClick={onClose}>Close</button></div>
      </div>
    </div>
  );
}

/** Opened by typing in a file cell: choose one or more files (each refused when too big). The files are handed back as they are:
 * the table keeps them and sends them to the server with the row. */
export function FileCellDialog({ kind, accept, onPick, onClose }: { kind: MediaKind; accept?: string; onPick: (files: File[]) => void; onClose: () => void }) {
  const [error, setError] = useState("");
  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (files.length === 0) return;
    const big = files.find((file) => file.size > CELL_FILE_LIMIT[kind]);
    if (big) return setError(`${big.name} is larger than ${CELL_FILE_LIMIT[kind] / (1024 * 1024)} MB.`);
    onPick(files);
  };
  return (
    <Dialog label={`Choose ${kind} files`} onClose={onClose}>
      <input type="file" multiple accept={accept ?? DEFAULT_ACCEPT[kind]} onChange={onChange} aria-label={`Choose ${kind} files`} />
      {error ? <p role="alert" style={{ margin: 0 }}>{error}</p> : null}
    </Dialog>
  );
}

/** Opens the file chooser at once (from a click or a key press), keeps the files of the right kind and size, and hands them back.
 * Files that are refused are reported with `onRefused`. */
export function pickFiles(kind: MediaKind, accept: string | undefined, onFiles: (files: File[]) => void, onRefused: (message: string) => void): void {
  const input = document.createElement("input");
  input.type = "file";
  input.multiple = true;
  input.accept = accept ?? DEFAULT_ACCEPT[kind];
  input.onchange = () => {
    const files = Array.from(input.files ?? []);
    const big = files.find((file) => file.size > CELL_FILE_LIMIT[kind]);
    if (big) onRefused(`${big.name} is larger than ${CELL_FILE_LIMIT[kind] / (1024 * 1024)} MB.`);
    const fits = files.filter((file) => file.size <= CELL_FILE_LIMIT[kind]);
    if (fits.length) onFiles(fits);
  };
  input.click();
}
