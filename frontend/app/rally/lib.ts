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
  shuttle: [number, number] | null; // the shuttle on this frame (0..1 of the frame), or null when it is not seen
}

export interface PeopleResult {
  status: "idle" | "running" | "done" | "failed";
  samples: PeopleSample[];
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
