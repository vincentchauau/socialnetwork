import { describe, expect, it } from "vitest";

import { sampleAt, shuttleAt, type PeopleSample } from "../../app/rally/lib";

describe("sampleAt", () => {
  const samples: PeopleSample[] = [
    { t_ms: 0, court: null, people: [] },
    { t_ms: 500, court: null, people: [{ id: 1, side: "near-left", x: 0.2, y: 0.8, box: [0.1, 0.5, 0.3, 0.8], x_m: 0.5, y_m: 1.1, score: 0.9 }] },
    { t_ms: 1000, court: null, people: [] },
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

describe("shuttleAt", () => {
  const points: [number, number, number][] = [[0, 0.1, 0.1], [40, 0.2, 0.1], [80, 0.3, 0.1]];

  it("interpolates between the two frames around the time", () => {
    expect(shuttleAt(points, 60)).toEqual([0.25, 0.1]);
  });

  it("gives the exact point at its own time", () => {
    expect(shuttleAt(points, 40)).toEqual([0.2, 0.1]);
  });

  it("gives nothing after the last point for longer than the gap allowed", () => {
    expect(shuttleAt(points, 1000)).toBeNull();
    expect(shuttleAt([], 10)).toBeNull();
  });
});
