export { errorText } from "@sn/api";

export const API = "/api/rally";

export interface MatchSummary {
  id: number;
  name: string;
  video_name: string;
  created_at: string;
}

/** A person on the court at one sample: the feet on the frame (x, y in 0..1) and on the court (x_m, y_m in metres). */
/** The colour of the ring and the label of each player, P1 to P4. */
export const PLAYER_COLORS: Record<number, string> = { 1: "#f5c518", 2: "#e8559a", 3: "#2fc4d9", 4: "#3ccf6f" };

export interface PersonOnCourt {
  id: number; // the label, 1 to 4: P1 to P4 (see backend identity.py)
  side: string;
  x: number; // the feet on the frame, 0..1
  y: number;
  box: [number, number, number, number]; // x1, y1, x2, y2 of the box around the person, 0..1 of the frame
  x_m: number;
  y_m: number;
  score: number;
}

export interface PeopleSample {
  t_ms: number;
  court: Point[] | null; // the four corners found on this frame, or null when no full court is in view
  people: PersonOnCourt[];
}

export interface PeopleResult {
  status: "idle" | "running" | "done" | "failed";
  samples: PeopleSample[];
  shuttle: ShuttlePoint[]; // the shuttle on each frame it is seen
}

/** The shuttle at one frame: [t_ms, x, y], with x and y in 0..1 of the frame. */
export type ShuttlePoint = [number, number, number];

/** Longer than this without a point, the shuttle is not shown: it has gone out of view or is lost. */
export const SHUTTLE_MAX_GAP_MS = 300;

/** The shuttle at `ms`, interpolated between the two points around it (points are in time order). */
export function shuttleAt(points: ShuttlePoint[], ms: number): [number, number] | null {
  const after = points.findIndex(([t]) => t >= ms);
  if (after === -1) return null;
  const next = points[after];
  if (next[0] === ms || after === 0) return next[0] - ms <= SHUTTLE_MAX_GAP_MS ? [next[1], next[2]] : null;
  const previous = points[after - 1];
  if (ms - previous[0] > SHUTTLE_MAX_GAP_MS && next[0] - ms > SHUTTLE_MAX_GAP_MS) return null;
  const share = (ms - previous[0]) / (next[0] - previous[0]);
  return [previous[1] + (next[1] - previous[1]) * share, previous[2] + (next[2] - previous[2]) * share];
}

/** The last sample at or before `ms` (samples are in time order), or null before the first one. */
export function sampleAt(samples: PeopleSample[], ms: number): PeopleSample | null {
  let found: PeopleSample | null = null;
  for (const sample of samples) {
    if (sample.t_ms > ms) break;
    found = sample;
  }
  return found;
}

/** A point on the video frame: x and y in 0..1 of its width and height. */
export type Point = [number, number];
