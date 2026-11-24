import { describe, expect, test } from "vitest";

import {
  bestOnColor,
  contrastBetween,
  generateAccents,
  hexToOklch,
  oklchToHex,
  relativeLuminance,
  resolveSurface,
} from "@sn/lib/theme";

describe("oklch conversion", () => {
  test.each(["#000000", "#ffffff", "#4f46e5", "#16a34a", "#f59e0b", "#808080"])("round-trips %s", (hex) => {
    const back = oklchToHex(hexToOklch(hex));
    const diff = [1, 3, 5].map((i) => Math.abs(parseInt(hex.slice(i, i + 2), 16) - parseInt(back.slice(i, i + 2), 16)));
    expect(Math.max(...diff)).toBeLessThanOrEqual(1);
  });

  test("out-of-gamut chroma is reduced instead of producing invalid hex", () => {
    expect(oklchToHex({ l: 0.9, c: 0.4, h: 150 })).toMatch(/^#[0-9a-f]{6}$/);
  });
});

describe("contrast", () => {
  test("black on white is 21:1", () => {
    expect(contrastBetween("#000000", "#ffffff")).toBeCloseTo(21, 5);
  });

  test("picks white text on dark and black text on light", () => {
    expect(bestOnColor("#101010").color).toBe("#ffffff");
    expect(bestOnColor("#f0f0f0").color).toBe("#000000");
  });
});

describe("resolveSurface", () => {
  test("keeps the picked color when it already meets the target", () => {
    const result = resolveSurface("#101010", 7);
    expect(result.surface).toBe("#101010");
    expect(result.adjusted).toBe(false);
  });

  test.each([3, 4.5, 7])("a mid-tone color reaches %s:1", (target) => {
    const result = resolveSurface("#7a7a7a", target);
    expect(contrastBetween(result.surface, result.onSurface)).toBeGreaterThanOrEqual(target);
  });

  test("a mid-tone color is only adjusted when black or white text falls short", () => {
    expect(resolveSurface("#7a7a7a", 4.5).adjusted).toBe(false);
    expect(resolveSurface("#7a7a7a", 7).adjusted).toBe(true);
  });
});

describe("generateAccents", () => {
  test("returns exactly `count` colors with the surface first", () => {
    const accents = generateAccents("#4f46e5", 5);
    expect(accents).toHaveLength(5);
    expect(accents[0]).toBe("#4f46e5");
  });

  test("accents share the surface luminance", () => {
    const target = relativeLuminance("#4f46e5");
    for (const accent of generateAccents("#4f46e5", 6)) {
      expect(Math.abs(relativeLuminance(accent) - target)).toBeLessThan(0.02);
    }
  });

  test("accents have distinct hues", () => {
    const hues = generateAccents("#4f46e5", 4).map((hex) => Math.round(hexToOklch(hex).h));
    expect(new Set(hues).size).toBe(4);
  });
});
