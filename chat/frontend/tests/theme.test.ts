import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_TOKENS,
  MIN_CONTRAST,
  PALETTES,
  THEME_STORAGE_KEY,
  applyTokens,
  buildTokens,
  contrastRatio,
  passesContrast,
  pickTheme,
  readStoredTheme,
  shuffleTheme,
  writeStoredTheme,
} from "../app/theme";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  document.documentElement.removeAttribute("style");
});

describe("contrast", () => {
  it("computes known ratios", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 0);
    expect(contrastRatio("#777777", "#777777")).toBeCloseTo(1, 5);
    expect(contrastRatio("#nothex", "#ffffff")).toBeNaN();
  });

  it("keeps the default plum theme and every built-in palette at AA in both variants", () => {
    expect(passesContrast(DEFAULT_TOKENS)).toBe(true);
    expect(PALETTES).toHaveLength(9);
    for (const shades of PALETTES) {
      expect(shades).toHaveLength(9);
      for (const variant of ["dark", "light"] as const) {
        const tokens = buildTokens(shades, variant);
        expect(contrastRatio(tokens.fg, tokens.bg)).toBeGreaterThanOrEqual(MIN_CONTRAST);
        expect(passesContrast(tokens)).toBe(true);
      }
    }
  });

  it("rejects low contrast and unparsable colours", () => {
    expect(passesContrast({ ...DEFAULT_TOKENS, fg: "#2a0020" })).toBe(false);
    expect(passesContrast({ ...DEFAULT_TOKENS, muted: "bogus" })).toBe(false);
  });
});

describe("pickTheme", () => {
  const grey = Array.from({ length: 9 }, () => "#808080"); // no contrast at all

  it("is random but deterministic for a given source", () => {
    expect(pickTheme(PALETTES, () => 0)).toMatchObject({ palette: 0, variant: "dark" });
    expect(pickTheme(PALETTES, () => 0.999999)).toMatchObject({ palette: 8, variant: "light" });
  });

  it("skips palettes below 4.5:1 and retries", () => {
    const choice = pickTheme([grey, PALETTES[2]], () => 0);
    expect(choice?.palette).toBe(1);
    expect(passesContrast(choice!.tokens)).toBe(true);
  });

  it("ignores palettes without 9 shades and returns null when none is usable", () => {
    expect(pickTheme([grey, ["#000000"]], () => 0.5)).toBeNull();
    expect(pickTheme([], () => 0.5)).toBeNull();
  });
});

describe("applying and persisting", () => {
  it("sets CSS variables on the root, not '*' rules", () => {
    applyTokens(buildTokens(PALETTES[0], "dark"));
    const root = document.documentElement.style;
    expect(root.getPropertyValue("--bg")).toBe(PALETTES[0][0]);
    expect(root.getPropertyValue("--fg")).toBe(PALETTES[0][8]);
    expect(root.getPropertyValue("--accent-2")).not.toBe("");
  });

  it("round-trips through localStorage and revalidates what it reads", () => {
    writeStoredTheme({ palette: 3, variant: "light" });
    expect(readStoredTheme()).toMatchObject({ palette: 3, variant: "light" });
    const bad = [
      "",
      "nope",
      "null",
      '{"palette":99,"variant":"dark"}',
      '{"palette":1.5,"variant":"dark"}',
      '{"palette":1,"variant":"neon"}',
      '{"palette":"1","variant":"dark"}',
    ];
    for (const raw of bad) {
      window.localStorage.setItem(THEME_STORAGE_KEY, raw);
      expect(readStoredTheme()).toBeNull();
    }
  });

  it("tolerates a failing localStorage on read and write", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readStoredTheme()).toBeNull();
    expect(() => writeStoredTheme({ palette: 0, variant: "dark" })).not.toThrow();
    expect(shuffleTheme()).toBe(true); // still applies for this page view
    expect(document.documentElement.style.getPropertyValue("--bg")).not.toBe("");
  });

  it("shuffleTheme applies and stores a pick, and refuses when every palette fails the guard", () => {
    expect(shuffleTheme()).toBe(true);
    expect(readStoredTheme()).not.toBeNull();
    document.documentElement.removeAttribute("style");
    window.localStorage.clear();
    const grey = Array.from({ length: 9 }, () => "#808080");
    expect(shuffleTheme([grey])).toBe(false);
    expect(document.documentElement.style.getPropertyValue("--bg")).toBe("");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });
});
