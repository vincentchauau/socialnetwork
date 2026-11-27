export { errorText } from "@sn/api";

export const API = "/api/rally";
export const MAX_HITS = 500;

export type Side = "A" | "B";

export interface Rally {
  id: number;
  number: number;
  start_ms: number;
  end_ms: number;
  hits: number;
  winner: Side;
}

export interface MatchSummary {
  id: number;
  name: string;
  video_name: string;
  created_at: string;
}

export interface Stats {
  rallies: number;
  score: Record<Side, number>;
  avg_hits: number;
  max_hits: number;
  avg_duration_ms: number;
  longest_rally_ms: number;
}

export interface MatchDetail extends MatchSummary {
  rallies: Rally[];
  stats: Stats;
  court: number[][] | null;
}

/** A rally being marked: the start is set first, then the end at the current time of the video. */
export interface Marks {
  startMs: number | null;
  endMs: number | null;
}

export const NO_MARKS: Marks = { startMs: null, endMs: null };

/** A point on the video frame: x and y in 0..1 of its width and height. */
export type Point = [number, number];

export const CORNER_NAMES = ["near left", "near right", "far right", "far left"] as const;

/** A click on the frame as a point in 0..1 (clamped, so a click just outside still counts as the edge). */
export function normalizedPoint(clientX: number, clientY: number, frame: { left: number; top: number; width: number; height: number }): Point {
  const x = frame.width > 0 ? (clientX - frame.left) / frame.width : 0;
  const y = frame.height > 0 ? (clientY - frame.top) / frame.height : 0;
  return [Math.min(Math.max(x, 0), 1), Math.min(Math.max(y, 0), 1)];
}

/** Milliseconds as m:ss.t (tenths of a second). */
export function formatMs(milliseconds: number): string {
  const total = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = String(total % 60).padStart(2, "0");
  const tenths = Math.floor((milliseconds % 1000) / 100);
  return `${minutes}:${seconds}.${tenths}`;
}

/** The end mark is valid only when it comes after the start mark. */
export function canSave(marks: Marks): boolean {
  return marks.startMs !== null && marks.endMs !== null && marks.endMs > marks.startMs;
}

/** The hits as typed: whole numbers between 0 and MAX_HITS, anything else reads as 0. */
export function hitsOf(text: string): number {
  const value = Math.trunc(Number(text));
  if (!Number.isFinite(value) || value < 0) return 0;
  return Math.min(value, MAX_HITS);
}
