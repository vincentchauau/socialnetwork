import { beforeEach, describe, expect, test } from "vitest";

import { contrastBetween } from "@sn/lib/theme";
import {
  DEFAULT_THEME,
  MAX_ACCENT_COUNT,
  THEME_STORAGE_KEY,
  buildTheme,
  loadTheme,
  parseTheme,
  saveTheme,
} from "@sn/lib/theme";

const TOKENS = ["--line", "--solid-0"];

describe("buildTheme", () => {
  test("sets the two names: --line and --solid-0..7", () => {
    const { vars } = buildTheme(DEFAULT_THEME);
    for (const token of TOKENS) expect(vars[token]).toMatch(/^#[0-9a-f]{6}$/);
    for (let i = 0; i < MAX_ACCENT_COUNT; i++) expect(vars[`--solid-${i}`]).toMatch(/^#[0-9a-f]{6}$/);
    expect(Object.keys(vars)).toHaveLength(1 + MAX_ACCENT_COUNT);
  });

  test.each([
    ["#ffffff", 4.5],
    ["#101010", 7],
    ["#2f5fd0", 4.5],
    ["#7a7a7a", 7],
    ["#f5c518", 7],
    ["#16a34a", 3],
  ] as const)("text on %s reaches the %s:1 target", (primary, contrast) => {
    const { vars } = buildTheme({ primary, count: 3, contrast });
    expect(contrastBetween(vars["--solid-0"], vars["--line"])).toBeGreaterThanOrEqual(contrast);
  });

  test.each(["#ffffff", "#101010", "#2f5fd0", "#f5c518"])("on %s the line color is black or white", (primary) => {
    const { vars } = buildTheme({ primary, count: 3, contrast: 4.5 });
    expect(["#000000", "#ffffff"]).toContain(vars["--line"]);
  });

  test("solid colors share one contrast with the line color", () => {
    const { vars } = buildTheme({ primary: "#2f5fd0", count: 4, contrast: 4.5 });
    const ratios = [0, 1, 2, 3].map((i) => contrastBetween(vars[`--solid-${i}`], vars["--line"]));
    expect(Math.max(...ratios) - Math.min(...ratios)).toBeLessThan(0.3);
    expect(vars["--solid-0"]).toBe("#2f5fd0");
  });

  test("reports when the picked color had to be adjusted", () => {
    expect(buildTheme({ primary: "#7a7a7a", count: 3, contrast: 7 }).adjusted).toBe(true);
    expect(buildTheme({ primary: "#101010", count: 3, contrast: 7 }).adjusted).toBe(false);
  });

  test("accent slots follow the count and cycle through the palette", () => {
    const { vars, accents } = buildTheme({ primary: "#2f5fd0", count: 2, contrast: 4.5 });
    expect(accents).toHaveLength(2);
    expect(vars["--solid-2"]).toBe(vars["--solid-0"]);
    expect(vars["--solid-3"]).toBe(vars["--solid-1"]);
  });
});

describe("parseTheme", () => {
  test("accepts a valid config and normalizes it", () => {
    expect(parseTheme({ primary: "#2F5FD0", count: 4, contrast: 7 })).toEqual({ primary: "#2f5fd0", count: 4, contrast: 7 });
  });

  test("clamps the count and falls back for a bad contrast", () => {
    expect(parseTheme({ primary: "#2f5fd0", count: 99, contrast: 5 })).toEqual({ primary: "#2f5fd0", count: MAX_ACCENT_COUNT, contrast: 4.5 });
    expect(parseTheme({ primary: "#2f5fd0", count: 0 })?.count).toBe(1);
  });

  test.each([null, undefined, "x", 5, {}, { primary: "red" }, { primary: "#12345" }, { primary: "url(javascript:1)" }])("rejects %p", (raw) => {
    expect(parseTheme(raw)).toBeNull();
  });
});

describe("storage", () => {
  beforeEach(() => localStorage.clear());

  test("saves only the config, not the variables, and loads it back", () => {
    const config = { primary: "#16a34a", count: 5, contrast: 7 as const };
    saveTheme(config);
    expect(loadTheme()).toEqual(config);
    expect(Object.keys(localStorage)).toEqual([THEME_STORAGE_KEY]);
  });

  test("returns null for corrupt storage and after clearing", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "{not json");
    expect(loadTheme()).toBeNull();
    expect(loadTheme()).toBeNull();
  });
});
