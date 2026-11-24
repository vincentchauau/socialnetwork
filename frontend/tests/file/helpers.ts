export const listing = (path: string, entries: unknown[], used = 1000, quota = 100 * 1024 * 1024) => ({
  path,
  entries,
  usage: { usedBytes: used, quotaBytes: quota },
});

export const file = (name: string, size = 10) => ({ name, type: "file", size, modifiedAt: "2026-01-01" });
export const folder = (name: string) => ({ name, type: "folder", size: 0, modifiedAt: "2026-01-01" });

export function fileOf(name: string, size: number): File {
  const f = new File(["x"], name, { type: "text/plain" });
  Object.defineProperty(f, "size", { value: size });
  return f;
}
