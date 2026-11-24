import { apiFetch, apiForm } from "@sn/api";

import { type Area, API, areaQuery, filesUrl, uploadUrl } from "./paths";
import type { Entry, FoundEntry, Listing, ShareEntry, TrashEntry, VersionEntry } from "./types";

export const listFiles = (path: string, area: Area = "mine") => apiFetch<Listing>(filesUrl(path, area));

export const createFolder = (path: string, name: string, area: Area = "mine") =>
  apiFetch<void>(`${API}/folder${areaQuery(area).replace("&", "?")}`, { method: "POST", body: JSON.stringify({ path, name }) });

export function uploadFile(path: string, file: File, area: Area = "mine", replace = false) {
  const form = new FormData();
  form.append("file", file);
  return apiForm<{ name: string; size: number; replaced?: boolean }>(`${uploadUrl(path, area)}${replace ? "&replace=true" : ""}`, form);
}

export const deleteEntry = (path: string, area: Area = "mine") => apiFetch<void>(filesUrl(path, area), { method: "DELETE" });

export const renameEntry = (path: string, newName: string, area: Area = "mine") =>
  apiFetch<void>(`${API}/rename${areaQuery(area).replace("&", "?")}`, { method: "POST", body: JSON.stringify({ path, newName }) });

export const listTrash = () => apiFetch<{ entries: TrashEntry[]; keepDays: number }>(`${API}/trash`);

export const restoreTrash = (id: string) => apiFetch<{ name: string; path: string }>(`${API}/trash/restore`, { method: "POST", body: JSON.stringify({ id }) });

export const eraseTrash = (id?: string) => apiFetch<void>(`${API}/trash${id ? `?id=${encodeURIComponent(id)}` : ""}`, { method: "DELETE" });

export const makeShare = (path: string, days?: number) => apiFetch<ShareEntry>(`${API}/share`, { method: "POST", body: JSON.stringify({ path, ...(days ? { days } : {}) }) });

export const listShares = () => apiFetch<{ shares: ShareEntry[] }>(`${API}/shares`);

export const takeBackShare = (token: string) => apiFetch<void>(`${API}/share/${encodeURIComponent(token)}`, { method: "DELETE" });

export const searchFiles = (q: string) => apiFetch<{ entries: FoundEntry[]; more: boolean }>(`${API}/search?q=${encodeURIComponent(q)}`);

export const listVersions = (path: string) => apiFetch<{ versions: VersionEntry[]; keepDays: number }>(`${API}/versions?path=${encodeURIComponent(path)}`);

export const restoreVersion = (id: string) => apiFetch<{ name: string; path: string }>(`${API}/versions/restore`, { method: "POST", body: JSON.stringify({ id }) });

export const dropVersion = (id: string) => apiFetch<void>(`${API}/versions?id=${encodeURIComponent(id)}`, { method: "DELETE" });

export const moveEntry = (path: string, toFolder: string, area: Area = "mine") =>
  apiFetch<{ moved: boolean }>(`${API}/move${areaQuery(area).replace("&", "?")}`, { method: "POST", body: JSON.stringify({ path, toFolder }) });

export const copyEntry = (path: string, toFolder: string, area: Area = "mine") =>
  apiFetch<{ copied: boolean; name: string }>(`${API}/copy${areaQuery(area).replace("&", "?")}`, { method: "POST", body: JSON.stringify({ path, toFolder }) });

export const searchFolder = (path: string, q: string, area: Area = "mine") =>
  apiFetch<{ entries: (Entry & { path: string })[]; more: boolean }>(`${API}/search-folder?path=${encodeURIComponent(path)}&q=${encodeURIComponent(q)}${areaQuery(area)}`);
