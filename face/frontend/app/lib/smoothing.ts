import type { Scores } from "./types";

export const SMOOTHING_FRAMES = 12;

const averageOf = (values: (number | null)[], decimals: number): number | null => {
  const present = values.filter((v): v is number => v !== null);
  if (!present.length) return null;
  const factor = 10 ** decimals;
  return Math.round((present.reduce((a, b) => a + b, 0) / present.length) * factor) / factor;
};

/** Returns a new window with `scores` appended, keeping at most `size` newest entries. */
export function pushWindow(window: readonly Scores[], scores: Scores, size = SMOOTHING_FRAMES): Scores[] {
  return [...window, scores].slice(-size);
}

/** Moving average of a window of frames; null fields are ignored unless the whole column is null. */
export function averageScores(window: readonly Scores[]): Scores | null {
  if (!window.length) return null;
  const col = (key: keyof Scores) => window.map((s) => s[key]);
  return {
    symmetry: averageOf(col("symmetry"), 0) ?? 0,
    eye: averageOf(col("eye"), 0),
    nose: averageOf(col("nose"), 0),
    mouth: averageOf(col("mouth"), 0),
    ear: averageOf(col("ear"), 0),
    angle: averageOf(col("angle"), 1),
  };
}
