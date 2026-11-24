import {
  EAR_LEFT, EAR_RIGHT, EYE_LEFT_CORNER, EYE_RIGHT_CORNER, FACE_OVAL,
  MOUTH_OUTER, NOSE_CENTER, NOSE_LEFT, NOSE_RIGHT,
} from "./landmarks";
import type { Landmark, Point, PositionHint, Scores } from "./types";

interface Midline {
  center: Point;
  /** Unit vector along the face's vertical-ish axis. */
  dir: Point;
}

const EPSILON = 1e-6;
const MIN_OVAL_POINTS = 3;
const FALLBACK_FACE_WIDTH = 100;
/** The face counts as upright when the nose line is within this many degrees of vertical. */
const POSITION_TOLERANCE_DEG = 2;

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const toPercent = (v: number) => Math.round(clamp01(v) * 100);
const mean = (values: readonly number[]) => values.reduce((a, b) => a + b, 0) / values.length;

export function toPixels(landmarks: readonly (Landmark | undefined)[], width: number, height: number): (Point | undefined)[] {
  return landmarks.map((l) => (l ? { x: l.x * width, y: l.y * height } : undefined));
}

/** Picks the existing points for the given indices, skipping missing ones. */
export function pick(points: readonly (Point | undefined)[], indices: readonly number[]): Point[] {
  return indices.map((i) => points[i]).filter((p): p is Point => Boolean(p));
}

export function faceWidthOf(points: readonly (Point | undefined)[]): number {
  const xs = pick(points, FACE_OVAL).map((p) => p.x);
  if (!xs.length) return FALLBACK_FACE_WIDTH;
  return Math.max(...xs) - Math.min(...xs) || FALLBACK_FACE_WIDTH;
}

/**
 * PCA midline: centroid plus the principal axis of the points that is closest to vertical.
 * Note: the original demo always picked the minor axis, which mirrored a tall face top-to-bottom.
 */
export function computeMidline(points: readonly Point[]): Midline {
  const n = points.length;
  const mx = mean(points.map((p) => p.x));
  const my = mean(points.map((p) => p.y));
  let sxx = 0;
  let sxy = 0;
  let syy = 0;
  for (const p of points) {
    const dx = p.x - mx;
    const dy = p.y - my;
    sxx += dx * dx;
    sxy += dx * dy;
    syy += dy * dy;
  }
  sxx /= n;
  sxy /= n;
  syy /= n;
  const trace = sxx + syy;
  const disc = Math.sqrt(Math.max(0, trace * trace - 4 * (sxx * syy - sxy * sxy)));
  const lambdaLarge = (trace + disc) / 2;
  let vx = 0;
  let vy = 1;
  if (Math.abs(sxy) > EPSILON) {
    vx = sxy;
    vy = lambdaLarge - sxx;
  } else if (sxx > syy) {
    vx = 1;
    vy = 0;
  }
  // A face midline is the principal axis closest to vertical (the other one is perpendicular).
  if (Math.abs(vy) < Math.abs(vx)) [vx, vy] = [-vy, vx];
  const len = Math.hypot(vx, vy) || 1;
  return { center: { x: mx, y: my }, dir: { x: vx / len, y: vy / len } };
}

/** How well the boundary points map onto themselves when mirrored across the midline (0..100). */
export function boundarySymmetry(boundary: readonly Point[], mid: Midline): number {
  if (!boundary.length) return 0;
  const theta = Math.atan2(mid.dir.x, mid.dir.y);
  const c = Math.cos(theta);
  const s = Math.sin(theta);
  const r = boundary.map((p) => {
    const dx = p.x - mid.center.x;
    const dy = p.y - mid.center.y;
    return { x: dx * c + dy * s, y: -dx * s + dy * c };
  });
  const xs = r.map((p) => p.x);
  const faceW = Math.max(...xs) - Math.min(...xs) || 1;
  const dists = r.map((p) => {
    const mirroredX = -p.x;
    let best = Infinity;
    let nearest = p;
    for (const q of r) {
      const score = Math.abs(q.x - mirroredX) + 0.5 * Math.abs(q.y - p.y);
      if (score < best) {
        best = score;
        nearest = q;
      }
    }
    return Math.hypot(nearest.x - mirroredX, nearest.y - p.y);
  });
  return toPercent(1 - mean(dists) / faceW);
}

/** Compares the mean horizontal distance of a left and a right group to the midline. */
export function featureLeftRightPct(left: readonly Point[], right: readonly Point[], centerX: number, faceW: number): number | null {
  if (!left.length || !right.length) return null;
  const ld = Math.abs(centerX - mean(left.map((p) => p.x)));
  const rd = Math.abs(mean(right.map((p) => p.x)) - centerX);
  return toPercent(1 - Math.abs(ld - rd) / faceW);
}

/** Acute angle (0..90) between the nose line and the horizontal; 90 = perfectly upright. */
export function noseAngle(points: readonly (Point | undefined)[]): number | null {
  const first = points[NOSE_CENTER[0]];
  const last = points[NOSE_CENTER[NOSE_CENTER.length - 1]];
  if (!first || !last) return null;
  const deg = Math.abs((Math.atan2(last.y - first.y, last.x - first.x) * 180) / Math.PI);
  return deg > 90 ? 180 - deg : deg;
}

export function positionHint(angle: number | null): PositionHint {
  if (angle === null) return "unknown";
  return Math.abs(angle - 90) <= POSITION_TOLERANCE_DEG ? "ok" : "tilted";
}

/** Full score set for one frame, or null when the face outline is not available. */
export function computeScores(landmarks: readonly (Landmark | undefined)[], width: number, height: number): Scores | null {
  const pts = toPixels(landmarks, width, height);
  const oval = pick(pts, FACE_OVAL);
  if (oval.length < MIN_OVAL_POINTS) return null;
  const mid = computeMidline(oval);
  const faceW = faceWidthOf(pts);
  const cx = mid.center.x;
  const outer = pick(pts, MOUTH_OUTER);
  const angle = noseAngle(pts);
  return {
    symmetry: boundarySymmetry(oval, mid),
    eye: featureLeftRightPct(pick(pts, [EYE_LEFT_CORNER]), pick(pts, [EYE_RIGHT_CORNER]), cx, faceW),
    nose: featureLeftRightPct(pick(pts, NOSE_LEFT), pick(pts, NOSE_RIGHT), cx, faceW),
    mouth: featureLeftRightPct(outer.filter((p) => p.x < cx), outer.filter((p) => p.x >= cx), cx, faceW),
    ear: featureLeftRightPct(pick(pts, EAR_LEFT), pick(pts, EAR_RIGHT), cx, faceW),
    angle: angle === null ? null : Math.round(angle * 10) / 10,
  };
}
