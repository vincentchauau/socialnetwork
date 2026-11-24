import { vi } from "vitest";

import { EAR_LEFT, EAR_RIGHT, EYE_LEFT, EYE_RIGHT, FACE_OVAL, MOUTH_INNER, MOUTH_OUTER, NOSE_CENTER, NOSE_LEFT, NOSE_RIGHT } from "../../app/face/lib/landmarks";
import type { Landmark, Scores } from "../../app/face/lib/types";

export const W = 640;
export const H = 480;

interface FaceOptions {
  /** Moves the left-eye/nose/mouth landmarks sideways (normalized units) to break symmetry. */
  skew?: number;
  /** Rotates the nose line by moving its last point sideways. */
  noseTilt?: number;
  /** Indices to remove (set to undefined) entirely. */
  drop?: number[];
}

/** 468 landmarks of a face that is perfectly mirrored around x = 0.5 unless options skew it. */
export function buildFace({ skew = 0, noseTilt = 0, drop = [] }: FaceOptions = {}): Landmark[] {
  const pts: Landmark[] = Array.from({ length: 468 }, () => ({ x: 0.5, y: 0.5 }));
  const n = FACE_OVAL.length;
  FACE_OVAL.forEach((idx, k) => {
    const theta = (2 * Math.PI * k) / n;
    pts[idx] = { x: 0.5 + 0.2 * Math.sin(theta), y: 0.5 - 0.3 * Math.cos(theta) };
  });
  EYE_LEFT.forEach((idx, k) => {
    const y = 0.42 + 0.01 * Math.sin(k);
    const dx = 0.1 + 0.02 * Math.cos(k);
    pts[idx] = { x: 0.5 - dx + skew, y };
    pts[EYE_RIGHT[k]] = { x: 0.5 + dx, y };
  });
  NOSE_LEFT.forEach((idx, k) => {
    const y = 0.5 + 0.01 * k;
    pts[idx] = { x: 0.5 - 0.04 + skew, y };
    pts[NOSE_RIGHT[k]] = { x: 0.5 + 0.04, y };
  });
  NOSE_CENTER.forEach((idx, k) => {
    pts[idx] = { x: 0.5 + (k === NOSE_CENTER.length - 1 ? noseTilt : 0), y: 0.35 + 0.04 * k };
  });
  pts[2] = { x: 0.5, y: 0.6 };
  MOUTH_OUTER.forEach((idx, k) => {
    const theta = (2 * Math.PI * k) / MOUTH_OUTER.length;
    pts[idx] = { x: 0.5 - 0.07 * Math.cos(theta) + (skew && k < 10 ? skew : 0), y: 0.7 - 0.02 * Math.sin(theta) };
  });
  MOUTH_INNER.forEach((idx, k) => {
    const theta = (2 * Math.PI * k) / MOUTH_INNER.length;
    pts[idx] = { x: 0.5 - 0.05 * Math.cos(theta), y: 0.7 - 0.01 * Math.sin(theta) };
  });
  // ear groups are subsets of the oval and are already mirrored.
  void EAR_LEFT;
  void EAR_RIGHT;
  const result = pts.slice();
  for (const idx of drop) result[idx] = undefined as unknown as Landmark;
  return result;
}

export const sampleScores = (over: Partial<Scores> = {}): Scores => ({
  symmetry: 90, eye: 95, nose: 96, mouth: 97, ear: 98, angle: 89.5, ...over,
});

/** A recording 2D context: every method is a spy, every property is writable. */
export function fakeContext() {
  const ctx = {
    clearRect: vi.fn(), drawImage: vi.fn(), beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(),
    closePath: vi.fn(), stroke: vi.fn(), fill: vi.fn(), arc: vi.fn(), quadraticCurveTo: vi.fn(),
    strokeStyle: "", fillStyle: "", lineWidth: 1,
  };
  return ctx as typeof ctx & CanvasRenderingContext2D;
}
