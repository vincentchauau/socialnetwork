import { describe, expect, it } from "vitest";

import { MAX_HITS, canSave, formatMs, hitsOf, sampleAt, type PeopleSample } from "../../app/rally/lib";

describe("sampleAt", () => {
  const samples: PeopleSample[] = [
    { t_ms: 0, court: null, shuttle: null, people: [] },
    { t_ms: 500, court: null, shuttle: null, people: [{ id: 1, side: "near-left", x: 0.2, y: 0.8, box: [0.1, 0.5, 0.3, 0.8], x_m: 0.5, y_m: 1.1, score: 0.9 }] },
    { t_ms: 1000, court: null, shuttle: null, people: [] },
  ];

  it("returns the last sample at or before the time", () => {
    expect(sampleAt(samples, 700)?.t_ms).toBe(500);
    expect(sampleAt(samples, 1000)?.t_ms).toBe(1000);
  });

  it("returns null before the first sample and for no samples", () => {
    expect(sampleAt(samples, -1)).toBeNull();
    expect(sampleAt([], 100)).toBeNull();
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
