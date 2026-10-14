import { afterEach, describe, expect, it } from "vitest";

import { COLORS, applyTheme, overwriteCSS, pickTheme, shuffleTheme } from "../app/theme";

afterEach(() => {
  document.head.querySelectorAll("style").forEach((el) => el.remove());
});

const rule = (selector: string) =>
  [...document.styleSheets]
    .flatMap((sheet) => [...sheet.cssRules] as CSSStyleRule[])
    .find((r) => r.selectorText === selector);

describe("palette", () => {
  it("is the original ChatWork palette: 13 ramps of 9 hex shades", () => {
    expect(COLORS).toHaveLength(13);
    for (const ramp of COLORS) {
      expect(ramp).toHaveLength(9);
      for (const shade of ramp) expect(shade).toMatch(/^#[0-9a-f]{6}$/);
    }
  });
});

describe("pickTheme", () => {
  it("uses shades 0/7/8 for a dark theme (background/border/text)", () => {
    const calls = [0, 0.1];
    const theme = pickTheme(() => calls.shift() ?? 0);
    expect(theme).toEqual({ background: COLORS[0][0], border: COLORS[0][7], text: COLORS[0][8] });
  });

  it("uses shades 8/1/0 for a light theme", () => {
    const calls = [0.5, 0.9];
    const theme = pickTheme(() => calls.shift() ?? 0);
    expect(theme).toEqual({ background: COLORS[6][8], border: COLORS[6][1], text: COLORS[6][0] });
  });

  it("never indexes past the last ramp", () => {
    const calls = [0.9999999, 0.9];
    expect(pickTheme(() => calls.shift() ?? 0).background).toBe(COLORS[12][8]);
  });

  it("works with the real random source", () => {
    expect(pickTheme().text).toMatch(/^#/);
  });
});

describe("overwriteCSS", () => {
  it("creates a rule, then replaces it instead of adding a second one", () => {
    overwriteCSS(".x", "color: red");
    overwriteCSS(".x", "color: blue");
    const rules = [...document.styleSheets].flatMap((s) => [...s.cssRules] as CSSStyleRule[]).filter((r) => r.selectorText === ".x");
    expect(rules).toHaveLength(1);
    expect(rules[0].style.color).toBe("blue");
  });

  it("reuses an existing inline sheet", () => {
    document.head.appendChild(document.createElement("style"));
    const before = document.styleSheets.length;
    overwriteCSS(".y", "color: red");
    expect(document.styleSheets.length).toBe(before);
  });
});

describe("applyTheme / shuffleTheme", () => {
  it("paints everything with the picked colours and inverts buttons on hover", () => {
    applyTheme({ background: "#200000", border: "#ff9999", text: "#ffcccc" });
    expect(rule("*")?.style.background).toContain("rgb(32, 0, 0)");
    expect(rule("*")?.style.color).toBe("rgb(255, 204, 204)");
    expect(rule("button:hover")?.style.color).toBe("rgb(32, 0, 0)");
    expect(rule(".selected")).toBeDefined();
  });

  it("shuffleTheme applies and returns the colours it picked", () => {
    const colors = shuffleTheme(() => 0.3);
    expect(colors.background).toMatch(/^#/);
    expect(rule("*")).toBeDefined();
  });
});
