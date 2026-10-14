import { apiFetch, apiForm } from "@sn/api";

import { WORK_API, filesUrl, uploadUrl } from "./paths";
import type { CallEvent, Listing, QueryResult, TableInfo, TablePage } from "./types";

export const listFiles = (path: string) => apiFetch<Listing>(filesUrl(path));

export const createFolder = (path: string, name: string) =>
  apiFetch<void>(`${WORK_API}/files/folder`, { method: "POST", body: JSON.stringify({ path, name }) });

export function uploadFile(path: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiForm<{ name: string; size: number }>(uploadUrl(path), form);
}

export const deleteEntry = (path: string) => apiFetch<void>(filesUrl(path), { method: "DELETE" });

export const renameEntry = (path: string, newName: string) =>
  apiFetch<void>(`${WORK_API}/files/rename`, { method: "POST", body: JSON.stringify({ path, newName }) });

export const listTables = () => apiFetch<TableInfo[]>(`${WORK_API}/db/tables`);

export function getTable(name: string, page: number, pageSize: number, q: string) {
  const query = `page=${page}&pageSize=${pageSize}&q=${encodeURIComponent(q)}`;
  return apiFetch<TablePage>(`${WORK_API}/db/tables/${encodeURIComponent(name)}?${query}`);
}

export const runQuery = (sql: string) =>
  apiFetch<QueryResult>(`${WORK_API}/db/query`, { method: "POST", body: JSON.stringify({ sql }) });

export function importCsv(table: string, file: File) {
  const form = new FormData();
  form.append("table", table);
  form.append("file", file);
  return apiForm<{ table: string; rows: number }>(`${WORK_API}/db/import`, form);
}

export const resetDatabase = () => apiFetch<void>(`${WORK_API}/db`, { method: "DELETE" });

export const listCalls = (limit = 50) => apiFetch<CallEvent[]>(`${WORK_API}/calls?limit=${limit}`);
