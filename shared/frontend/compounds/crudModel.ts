import { ApiError } from "../api";
import { registerScoped } from "../lib/i18n";
import bundles from "./crud.locales.json";

export const crudTr = registerScoped("crud", bundles);

export type ColumnType = "string" | "text" | "int" | "float" | "bool" | "datetime" | "json" | "bytes";

export interface ColumnInfo {
  name: string;
  type: ColumnType;
  nullable: boolean;
  readonly: boolean;
  secret: boolean;
  /** The table this column points to and the column that names its rows (optional: older servers omit it). */
  ref?: { table: string; label: string; key?: string };
  /** A picture column: where its preview comes from and, when it can be replaced, where the new file goes (URLs with `{column}` / `{pk}` placeholders; `@self`: the value is the URL). */
  media?: MediaInfo;
}

export type MediaKind = "image" | "video" | "audio" | "file";

export interface MediaInfo {
  /** How the file is shown; default "image". */
  kind?: MediaKind;
  preview?: string;
  replace?: string;
  accept?: string;
}

export interface TableInfo {
  name: string;
  label: string;
  pk: string[];
  /** The letters an admin may write: C create, U update, D delete ("CRUD", "RUD" or "RD"). */
  /** Whether the person looking may change rows of this table (the server decides row by row). */
  writable: boolean;
  columns: ColumnInfo[];
  /** Rows are created by uploading files (multipart `file`, POST) to this path instead of the generic form. */
  create_via?: string;
  create_label?: string;
  /** The form fields (besides the file) the upload route takes: the Add form shows exactly these, and sends them with the file. */
  create_fields?: string[];
}

export type Row = Record<string, unknown>;
/** Per reference column: the text of each value (`{user_id: {"2": "Binh_Phan"}}`). Optional in every response. */
export type Labels = Record<string, Record<string, string>>;
export type Draft = Record<string, string | boolean>;

/** The path part of a row: the key columns joined with "~". */
export function pkOf(table: TableInfo, row: Row): string {
  return table.pk.map((column) => encodeURIComponent(String(row[column]))).join("~");
}

/** The words of a failed call: the server's `detail` (a text, or the list of problems of a 422), else the error's own message. */
export function detailText(error: unknown): string {
  if (!(error instanceof ApiError)) return crudTr("load_failed");
  const detail = (error.body as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((item) => (typeof item === "string" ? item : String((item as { msg?: unknown }).msg ?? JSON.stringify(item)))).join("; ");
  }
  return error.message;
}

/** "image_name" -> "Image name", "user_id" -> "User": underscores to spaces, a trailing "id" dropped, first letter capital. */
export function humanize(name: string): string {
  const words = name.split("_").filter(Boolean);
  if (words.length > 1 && words[words.length - 1].toLowerCase() === "id") words.pop();
  const text = words.join(" ") || name;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The last segment of a path or address, without its query: "/media/2024/a.png?v=1" -> "a.png". */
export function fileName(path: string): string {
  const clean = path.split(/[?#]/, 1)[0].replace(/\/+$/, "");
  const last = clean.slice(clean.lastIndexOf("/") + 1);
  return last || path;
}

export const mediaKind = (media: MediaInfo): MediaKind => media.kind ?? "image";

/** Fills `{column}` and `{pk}` in a media URL from a row. */
export function fillUrl(template: string, table: TableInfo, row: Row): string {
  return template.replace(/\{(\w+)\}/g, (whole, key: string) => {
    if (key === "pk") return pkOf(table, row);
    return key in row ? encodeURIComponent(String(row[key])) : whole;
  });
}

/** The address of the picture of a media column in a row, or null. `stamp` busts the browser cache after a replacement. */
export function mediaSrc(table: TableInfo, column: ColumnInfo, row: Row, stamp?: number): string | null {
  const preview = column.media?.preview;
  if (!preview) return null;
  const value = row[column.name];
  let url: string;
  if (preview === "@self") {
    if (typeof value !== "string" || value === "") return null;
    url = value;
  } else url = fillUrl(preview, table, row);
  if (!stamp) return url;
  return `${url}${url.includes("?") ? "&" : "?"}v=${stamp}`;
}

const LOCAL_INPUT = /^\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d)?$/;
const two = (n: number) => String(n).padStart(2, "0");

/** An ISO date-time as the value of a datetime-local input (the person's local time); other text is returned as it is. */
export function toLocalInput(value: unknown): string {
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())}T${two(date.getHours())}:${two(date.getMinutes())}`;
}

/** The value of a datetime-local input as an ISO string (UTC); null when it is not a date-time. */
export function localInputToIso(text: string): string | null {
  if (!LOCAL_INPUT.test(text)) return null;
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/** Whether a column is shown locked (not editable) in the form of a row. */
export function isLocked(table: TableInfo, column: ColumnInfo, editing: boolean): boolean {
  return column.readonly || column.type === "bytes" || (editing && table.pk.includes(column.name));
}

/** The starting values of the form of a row (or of a new row when `row` is null). */
export function draftOf(table: TableInfo, row: Row | null): Draft {
  const draft: Draft = {};
  for (const column of table.columns) {
    const value = row?.[column.name];
    if (column.type === "bool") draft[column.name] = Boolean(value);
    else if (column.secret || column.type === "bytes" || value === null || value === undefined) draft[column.name] = "";
    else if (column.type === "json") draft[column.name] = JSON.stringify(value);
    else draft[column.name] = column.type === "datetime" && !column.readonly ? toLocalInput(value) : String(value);
  }
  return draft;
}

/** The values to send for a draft, or the text of what is wrong with it. Read-only columns are never sent; an empty secret is left as it is. */
export function valuesOf(table: TableInfo, draft: Draft, editing: boolean): { values: Row } | { error: string } {
  const values: Row = {};
  for (const column of table.columns) {
    if (column.readonly || column.type === "bytes") continue;
    if (editing && table.pk.includes(column.name)) continue;
    const raw = draft[column.name];
    if (column.type === "bool") {
      values[column.name] = Boolean(raw);
      continue;
    }
    const text = String(raw ?? "");
    if (text === "") {
      if (column.secret && editing) continue;
      if (column.nullable) values[column.name] = null;
      else if (column.type === "string" || column.type === "text") values[column.name] = "";
      else if (!editing) return { error: crudTr("required", { name: column.name }) };
      continue;
    }
    if (column.type === "int" || column.type === "float") {
      const number = Number(text);
      if (Number.isNaN(number) || (column.type === "int" && !Number.isInteger(number))) return { error: crudTr("invalid_number", { name: column.name }) };
      values[column.name] = number;
    } else if (column.type === "json") {
      try {
        values[column.name] = JSON.parse(text);
      } catch {
        return { error: crudTr("invalid_json", { name: column.name }) };
      }
    } else if (column.type === "datetime") {
      values[column.name] = LOCAL_INPUT.test(text) ? (localInputToIso(text) ?? text) : text;
    } else values[column.name] = text;
  }
  return { values };
}

/** The value a json column is saved with, from the text typed in it: an empty text is null, anything else must be valid JSON (else the error says so). */
export function jsonCellValue(column: ColumnInfo, text: string): unknown {
  if (text.trim() === "") return null;
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(crudTr("invalid_json", { name: column.name }));
  }
}

/** The text of a value in an input or a cell: null is empty, an object or an array is its JSON (not "[object Object]"), anything else its text. */
export function textOfValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
