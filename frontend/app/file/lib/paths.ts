import { tr } from "../i18n";
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const MAX_NAME = 100;
export const MAX_DEPTH = 6;
export const API = "/api/file";

interface Crumb {
  label: string;
  path: string;
}

/** Splits a virtual path into its components (ignores empty ones). */
export function segments(path: string): string[] {
  return path.split("/").filter(Boolean);
}

export function joinPath(dir: string, name: string): string {
  return `${dir === "/" ? "" : dir}/${name}`;
}

export function breadcrumbs(path: string): Crumb[] {
  const parts = segments(path);
  return [
    { label: "data", path: "/" },
    ...parts.map((label, i) => ({ label, path: "/" + parts.slice(0, i + 1).join("/") })),
  ];
}

/** Returns a Vietnamese problem description, or null when the name is acceptable. */
export function nameProblem(name: string): string | null {
  if (!name.trim()) return tr("hay_nhap_ten");
  if (name.length > MAX_NAME) return tr("ten_khong_duoc_dai_qua_max", { MAX_NAME });
  if (name === "../../work/lib" || name === "../../work" || /[/\\]/.test(name)) {
    return tr("ten_khong_duoc_chua_dau_hoac");
  }
  return null;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** The area of the files: the own one of the person (nothing is added to the address), or the data of the server (an admin only). */
export type Area = "mine" | "data";
export const areaQuery = (area: Area): string => (area === "data" ? "&area=data" : "");

export function filesUrl(path: string, area: Area = "mine"): string {
  return `${API}/entries?path=${encodeURIComponent(path)}${areaQuery(area)}`;
}

export function downloadUrl(path: string, area: Area = "mine"): string {
  return `${API}/download?path=${encodeURIComponent(path)}${areaQuery(area)}`;
}

export function uploadUrl(path: string, area: Area = "mine"): string {
  return `${API}/upload?path=${encodeURIComponent(path)}${areaQuery(area)}`;
}
