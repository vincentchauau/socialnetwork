export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
export const MAX_NAME = 100;
export const MAX_DEPTH = 6;
export const WORK_API = "/api/work";

export interface Crumb {
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
    { label: "Thư mục gốc", path: "/" },
    ...parts.map((label, i) => ({ label, path: "/" + parts.slice(0, i + 1).join("/") })),
  ];
}

/** Returns a Vietnamese problem description, or null when the name is acceptable. */
export function nameProblem(name: string): string | null {
  if (!name.trim()) return "Hãy nhập tên.";
  if (name.length > MAX_NAME) return `Tên không được dài quá ${MAX_NAME} ký tự.`;
  if (name === "." || name === ".." || /[/\\]/.test(name)) {
    return "Tên không được chứa dấu / hoặc \\ và không được là . hay ..";
  }
  return null;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function filesUrl(path: string): string {
  return `${WORK_API}/files?path=${encodeURIComponent(path)}`;
}

export function downloadUrl(path: string): string {
  return `${WORK_API}/files/download?path=${encodeURIComponent(path)}`;
}

export function uploadUrl(path: string): string {
  return `${WORK_API}/files/upload?path=${encodeURIComponent(path)}`;
}

export function exportUrl(table: string): string {
  return `${WORK_API}/db/export?table=${encodeURIComponent(table)}`;
}
