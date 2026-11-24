import type { ColumnInfo, Row, TableInfo } from "./crudModel";
import { jsonCellValue, pkOf } from "./crudModel";

/** Rows per page of the table. */
/** The most rows one request creates or changes (BATCH_MAX on the server). */
export const TABLE_MAX_ROWS = 200;

/** The key of a row as a body reads it: its key columns joined with "~", not encoded. */
export function rawPk(table: TableInfo, row: Row): string {
  return table.pk.map((column) => String(row[column])).join("~");
}

/** The path form of a key: each part encoded, as the row's own address needs it. */
export const pathPk = (key: string): string => key.split("~").map(encodeURIComponent).join("~");

/** The columns a person fills in: every column that is not a key, not read-only and not secret (files and references included). */
export function tableColumns(table: TableInfo): ColumnInfo[] {
  return table.columns.filter((column) => !column.readonly && !column.secret && !table.pk.includes(column.name));
}

/** The values one row sends: an emptied nullable text is null, a json text is parsed (invalid json throws); a column not changed is not sent. */
export function changedValues(columns: ColumnInfo[], changes: Record<string, string>): Record<string, unknown> {
  return Object.fromEntries(columns.filter((column) => column.name in changes).map((column) => {
    const text = changes[column.name];
    if (column.type === "json") return [column.name, jsonCellValue(column, text)];
    return [column.name, text.trim() === "" && column.nullable ? null : text];
  }));
}

/** The kind of file a file name is: a picture, audio, video, or none of those. */
export function kindOfFile(name: string): "image" | "audio" | "video" | null {
  const extension = name.slice(name.lastIndexOf(".")).toLowerCase();
  if ([".jpg", ".jpeg", ".png", ".gif", ".webp"].includes(extension)) return "image";
  if ([".mp3", ".wav", ".ogg", ".m4a", ".flac"].includes(extension)) return "audio";
  if ([".mp4", ".webm", ".mov", ".mkv"].includes(extension)) return "video";
  return null;
}

export interface FolderRow {
  /** The text of the first text column: the name of the folder (or of its sub-folder). */
  title: string;
  files: File[];
}

export interface FolderPlan {
  rows: FolderRow[];
  /** Files that were not put into any row, by their path. */
  skipped: string[];
}

/** The rows a chosen folder makes. Each sub-folder is one row (its files are that row's pictures, audio or video); a folder with no
 * sub-folder is one row itself. The name of the row goes into the first text column. */
export function folderPlan(picked: { path: string; file: File }[]): FolderPlan {
  const parts = picked.map((entry) => ({ ...entry, segments: entry.path.split("/") }));
  const subfolders = parts.filter((entry) => entry.segments.length >= 3);
  const skipped: string[] = [];
  if (subfolders.length === 0) {
    const root = picked[0]?.path.split("/")[0] ?? "";
    const files = parts.map((entry) => entry.file);
    return { rows: files.length ? [{ title: root, files }] : [], skipped };
  }
  const groups = new Map<string, File[]>();
  for (const entry of parts) {
    if (entry.segments.length < 3) {
      skipped.push(entry.path);
      continue;
    }
    const folder = entry.segments[1];
    groups.set(folder, [...(groups.get(folder) ?? []), entry.file]);
  }
  return { rows: [...groups].map(([title, files]) => ({ title, files })), skipped };
}

/** Which of the files of a row a picture, audio or video column takes: the files of the kind the column holds. */
export function filesFor(column: ColumnInfo, files: File[]): { keep: File[]; skipped: File[] } {
  const kind = column.media?.kind ?? "image";
  const keep = files.filter((file) => kindOfFile(file.name) === kind);
  return { keep, skipped: files.filter((file) => !keep.includes(file)) };
}

/** The first text column (not a key, a file or a reference): where a folder's name goes. */
export function titleColumn(table: TableInfo): ColumnInfo | undefined {
  return tableColumns(table).find((column) => !column.media && !column.ref && column.type === "string");
}

export const keyOf = (table: TableInfo, row: Row): string => rawPk(table, row) || pkOf(table, row);
