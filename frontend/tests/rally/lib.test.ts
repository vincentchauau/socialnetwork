import { describe, expect, it } from "vitest";

import { MAX_HITS, canSave, formatMs, hitsOf, normalizedPoint } from "../../app/rally/lib";

describe("normalizedPoint", () => {
  const frame = { left: 100, top: 50, width: 400, height: 200 };

  it("maps a click inside the frame to 0..1 of its size", () => {
    expect(normalizedPoint(300, 150, frame)).toEqual([0.5, 0.5]);
    expect(normalizedPoint(100, 250, frame)).toEqual([0, 1]);
  });

  it("clamps a click outside the frame to its edge", () => {
    expect(normalizedPoint(50, 10, frame)).toEqual([0, 0]);
    expect(normalizedPoint(600, 400, frame)).toEqual([1, 1]);
  });
});

describe("formatMs", () => {
  it("shows minutes, seconds and tenths", () => {
    expect(formatMs(0)).toBe("0:00.0");
    expect(formatMs(800)).toBe("0:00.8");
    expect(formatMs(65_400)).toBe("1:05.4");
  });
});

describe("canSave", () => {
  it("needs both marks and an end after the start", () => {
    expect(canSave({ startMs: null, endMs: null })).toBe(false);
    expect(canSave({ startMs: 1000, endMs: null })).toBe(false);
    expect(canSave({ startMs: 1000, endMs: 1000 })).toBe(false);
    expect(canSave({ startMs: 1000, endMs: 1800 })).toBe(true);
  });
});

describe("hitsOf", () => {
  it("keeps whole numbers within the limit", () => {
    expect(hitsOf("7")).toBe(7);
    expect(hitsOf("7.9")).toBe(7);
    expect(hitsOf(String(MAX_HITS + 50))).toBe(MAX_HITS);
  });

  it("reads anything else as zero", () => {
    expect(hitsOf("")).toBe(0);
    expect(hitsOf("-3")).toBe(0);
    expect(hitsOf("abc")).toBe(0);
  });
});
