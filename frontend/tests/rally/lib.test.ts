import { describe, expect, it } from "vitest";

import { sampleAt, type PeopleSample } from "../../app/rally/lib";

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
