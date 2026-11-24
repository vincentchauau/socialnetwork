/** A MediaPipe normalized landmark (0..1 in image space). */
export interface Landmark {
  x: number;
  y: number;
  z?: number;
}

export interface Point {
  x: number;
  y: number;
}

/** Geometry scores, all 0..100 except angle (0..90 degrees). null = not measurable. */
export interface Scores {
  symmetry: number;
  eye: number | null;
  nose: number | null;
  mouth: number | null;
  ear: number | null;
  angle: number | null;
}

/** A saved measurement as returned by the backend. */
export interface Measurement extends Scores {
  id: number | string;
  createdAt: string;
  /** The person's own words about the reading. */
  note?: string;
}

export type PositionHint = "ok" | "tilted" | "unknown";
