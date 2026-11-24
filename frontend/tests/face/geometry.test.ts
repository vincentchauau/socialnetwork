import { describe, expect, it } from "vitest";

import {
  boundarySymmetry, computeMidline, computeScores, faceWidthOf, featureLeftRightPct,
  noseAngle, pick, positionHint, toPixels,
} from "../../app/face/lib/geometry";
import { FACE_OVAL, NOSE_CENTER } from "../../app/face/lib/landmarks";
import { H, W, buildFace } from "./helpers";

const pointsOf = (landmarks: ReturnType<typeof buildFace>) => toPixels(landmarks, W, H);

describe("toPixels / pick / faceWidthOf", () => {
  it("scales normalized landmarks to pixels", () => {
    expect(toPixels([{ x: 0.5, y: 0.25 }], 200, 100)).toEqual([{ x: 100, y: 25 }]);
  });
  it("skips missing indices", () => {
    expect(pick([{ x: 1, y: 1 }, undefined], [0, 1, 5])).toEqual([{ x: 1, y: 1 }]);
  });
  it("measures the oval width and falls back when empty", () => {
    expect(faceWidthOf(pointsOf(buildFace()))).toBeCloseTo(0.4 * W, 0);
    expect(faceWidthOf([])).toBe(100);
  });
  it("falls back to 100 when all oval points share one x", () => {
    const pts: { x: number; y: number }[] = [];
    for (const i of FACE_OVAL) pts[i] = { x: 7, y: 1 };
    expect(faceWidthOf(pts)).toBe(100);
  });
});

describe("computeMidline", () => {
  const oval = (landmarks: ReturnType<typeof buildFace>) => pick(pointsOf(landmarks), FACE_OVAL);

  it("finds a vertical midline through the centre of a symmetric tall face", () => {
    const mid = computeMidline(oval(buildFace()));
    expect(mid.center.x).toBeCloseTo(0.5 * W, 3);
    expect(Math.abs(mid.dir.x)).toBeLessThan(1e-3);
    expect(Math.abs(mid.dir.y)).toBeCloseTo(1, 3);
  });
  it("handles a tilted point cloud (non-zero covariance)", () => {
    const mid = computeMidline([{ x: 0, y: 0 }, { x: 1, y: 2 }, { x: 2, y: 4 }]);
    expect(mid.dir.x).toBeCloseTo(1 / Math.sqrt(5), 3);
    expect(mid.dir.y).toBeCloseTo(2 / Math.sqrt(5), 3);
  });
  it("still prefers the vertical axis for a wide axis-aligned cloud", () => {
    const mid = computeMidline([{ x: -4, y: 0 }, { x: 4, y: 0 }, { x: 0, y: 1 }, { x: 0, y: -1 }]);
    expect(mid.dir.x).toBeCloseTo(0);
    expect(mid.dir.y).toBeCloseTo(1);
  });
  it("takes the perpendicular axis when the principal axis is closer to horizontal", () => {
    const mid = computeMidline([{ x: 0, y: 0 }, { x: 4, y: 1 }, { x: 8, y: 2 }]);
    expect(Math.abs(mid.dir.y)).toBeGreaterThan(Math.abs(mid.dir.x));
  });
  it("survives a single point", () => {
    expect(computeMidline([{ x: 3, y: 4 }]).dir).toEqual({ x: 0, y: 1 });
  });
});

describe("boundarySymmetry", () => {
  it("scores a perfectly mirrored boundary at ~100", () => {
    const oval = pick(pointsOf(buildFace()), FACE_OVAL);
    expect(boundarySymmetry(oval, computeMidline(oval))).toBeGreaterThanOrEqual(99);
  });
  it("scores a lopsided boundary lower", () => {
    const oval = pick(pointsOf(buildFace()), FACE_OVAL).map((p) => (p.x > 0.5 * W ? { x: 0.5 * W + (p.x - 0.5 * W) * 2, y: p.y } : p));
    expect(boundarySymmetry(oval, computeMidline(oval))).toBeLessThan(97);
  });
  it("returns 0 for no points", () => {
    expect(boundarySymmetry([], { center: { x: 0, y: 0 }, dir: { x: 0, y: 1 } })).toBe(0);
  });
});

describe("featureLeftRightPct", () => {
  it("is 100 for equal distances and drops with the offset", () => {
    expect(featureLeftRightPct([{ x: 40, y: 0 }], [{ x: 60, y: 0 }], 50, 100)).toBe(100);
    expect(featureLeftRightPct([{ x: 40, y: 0 }], [{ x: 70, y: 0 }], 50, 100)).toBe(90);
  });
  it("clamps at 0 and returns null when a side is missing", () => {
    expect(featureLeftRightPct([{ x: 49, y: 0 }], [{ x: 500, y: 0 }], 50, 10)).toBe(0);
    expect(featureLeftRightPct([], [{ x: 1, y: 0 }], 0, 1)).toBeNull();
    expect(featureLeftRightPct([{ x: 1, y: 0 }], [], 0, 1)).toBeNull();
  });
});

describe("noseAngle / positionHint", () => {
  const nose = (lastX: number) => {
    const pts: { x: number; y: number }[] = [];
    pts[NOSE_CENTER[0]] = { x: 0, y: 0 };
    pts[NOSE_CENTER[NOSE_CENTER.length - 1]] = { x: lastX, y: 100 };
    return pts;
  };
  it("is 90 for a vertical nose line and folds tilts to 0..90", () => {
    expect(noseAngle(nose(0))).toBeCloseTo(90);
    expect(noseAngle(nose(100))).toBeCloseTo(45);
    expect(noseAngle(nose(-100))).toBeCloseTo(45);
  });
  it("is null when an endpoint is missing", () => {
    expect(noseAngle([])).toBeNull();
  });
  it("classifies the position", () => {
    expect(positionHint(null)).toBe("unknown");
    expect(positionHint(89)).toBe("ok");
    expect(positionHint(80)).toBe("tilted");
  });
});

describe("computeScores", () => {
  it("rates a perfectly mirrored upright face ~100 everywhere with a 90 degree angle", () => {
    const s = computeScores(buildFace(), W, H);
    expect(s).not.toBeNull();
    expect(s!.symmetry).toBeGreaterThanOrEqual(99);
    for (const v of [s!.eye, s!.nose, s!.mouth, s!.ear]) expect(v).toBeGreaterThanOrEqual(97);
    expect(s!.angle).toBeCloseTo(90, 0);
  });
  it("scores a shifted face lower", () => {
    const base = computeScores(buildFace(), W, H)!;
    const shifted = computeScores(buildFace({ skew: 0.05 }), W, H)!;
    expect(shifted.eye!).toBeLessThan(base.eye!);
    expect(shifted.nose!).toBeLessThan(base.nose!);
    expect(shifted.mouth!).toBeLessThan(base.mouth!);
  });
  it("reports a smaller angle when the nose line is tilted", () => {
    const s = computeScores(buildFace({ noseTilt: 0.1 }), W, H)!;
    expect(s.angle!).toBeLessThan(85);
  });
  it("gives null for features whose landmarks are missing, and null overall without an oval", () => {
    const noEyes = computeScores(buildFace({ drop: [33, 263] }), W, H)!;
    expect(noEyes.eye).toBeNull();
    const noNose = computeScores(buildFace({ drop: [168, 1] }), W, H)!;
    expect(noNose.angle).toBeNull();
    expect(computeScores(buildFace({ drop: FACE_OVAL }), W, H)).toBeNull();
    expect(computeScores([], W, H)).toBeNull();
  });
});
