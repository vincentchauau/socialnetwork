export const MAX_TAGS = 10;
export const MAX_TAG_LENGTH = 30;
export const PROGRESS_SAVE_INTERVAL_MS = 10_000;
/** Do not resume if the viewer was this close to the end; start over instead. */
export const RESUME_END_MARGIN_SECONDS = 3;

const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 3600;
const KB = 1024;
const MB = KB * 1024;

const pad = (value: number): string => String(value).padStart(2, "0");

export function formatDuration(totalSeconds: number): string {
  const safe = Number.isFinite(totalSeconds) && totalSeconds > 0 ? Math.floor(totalSeconds) : 0;
  const hours = Math.floor(safe / SECONDS_PER_HOUR);
  const minutes = Math.floor((safe % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE);
  const seconds = safe % SECONDS_PER_MINUTE;
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${minutes}:${pad(seconds)}`;
}

export function formatSize(bytes: number): string {
  return bytes >= MB ? `${(bytes / MB).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / KB))} KB`;
}

/** Comma- or space-separated tags: trimmed, lower-cased, de-duplicated. */
export function parseTags(input: string): string[] {
  const tags = input
    .split(/[,\s]+/)
    .map((tag) => tag.trim().toLowerCase())
    .filter((tag) => tag.length > 0);
  return Array.from(new Set(tags));
}

export function validateTags(tags: string[]): string | null {
  if (tags.length > MAX_TAGS) return `Use at most ${MAX_TAGS} tags`;
  if (tags.some((tag) => tag.length > MAX_TAG_LENGTH)) {
    return `Each tag can be at most ${MAX_TAG_LENGTH} characters`;
  }
  return null;
}

export function shouldSaveProgress(nowMs: number, lastSavedMs: number): boolean {
  return nowMs - lastSavedMs >= PROGRESS_SAVE_INTERVAL_MS;
}

/** Where playback should resume, or 0 when there is nothing worth resuming. */
export function resumePosition(saved: number, duration: number): number {
  if (!(saved > 0)) return 0;
  if (Number.isFinite(duration) && saved >= duration - RESUME_END_MARGIN_SECONDS) return 0;
  return saved;
}
