export interface Oklch {
  l: number;
  c: number;
  h: number;
}

/** WCAG 2 contrast targets: large text and icons, AA body text, AAA body text. */
const CONTRAST_LEVELS = [3, 4.5, 7] as const;
export type ContrastLevel = (typeof CONTRAST_LEVELS)[number];
const DEFAULT_CONTRAST: ContrastLevel = 4.5;

export function isContrastLevel(value: unknown): value is ContrastLevel {
  return CONTRAST_LEVELS.some((level) => level === value);
}

export function isHexColor(value: unknown): value is string {
  return typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value);
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

function srgbToLinear(channel: number): number {
  return channel <= 0.04045 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4);
}

function linearToSrgb(channel: number): number {
  return channel <= 0.0031308 ? channel * 12.92 : 1.055 * Math.pow(channel, 1 / 2.4) - 0.055;
}

function hexToLinearRgb(hex: string): [number, number, number] {
  const c = hex.replace("#", "");
  return [0, 2, 4].map((i) => srgbToLinear(parseInt(c.substring(i, i + 2), 16) / 255)) as [number, number, number];
}

/** WCAG relative luminance, 0 (black) to 1 (white). */
export function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToLinearRgb(hex);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast ratio between two luminances, always >= 1. */
export function contrastRatio(l1: number, l2: number): number {
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

/** WCAG contrast ratio between two hex colors. */
export function contrastBetween(a: string, b: string): number {
  return contrastRatio(relativeLuminance(a), relativeLuminance(b));
}

export function hexToOklch(hex: string): Oklch {
  const [r, g, b] = hexToLinearRgb(hex);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  const c = Math.hypot(a, bb);
  const h = c < 1e-4 ? 0 : ((Math.atan2(bb, a) * 180) / Math.PI + 360) % 360;
  return { l: L, c, h };
}

/** Linear sRGB for an OKLCH color, or null when it falls outside the sRGB gamut. */
function oklchToLinearRgb({ l, c, h }: Oklch): [number, number, number] | null {
  const a = c * Math.cos((h * Math.PI) / 180);
  const b = c * Math.sin((h * Math.PI) / 180);
  const l_ = Math.pow(l + 0.3963377774 * a + 0.2158037573 * b, 3);
  const m_ = Math.pow(l - 0.1055613458 * a - 0.0638541728 * b, 3);
  const s_ = Math.pow(l - 0.0894841775 * a - 1.291485548 * b, 3);
  const rgb: [number, number, number] = [
    4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
    -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
    -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_,
  ];
  const eps = 1e-6;
  return rgb.every((v) => v >= -eps && v <= 1 + eps) ? rgb : null;
}

/** Convert OKLCH to hex; an out-of-gamut color keeps L and H and loses chroma until it fits. */
export function oklchToHex(color: Oklch): string {
  const l = clamp01(color.l);
  let rgb = oklchToLinearRgb({ ...color, l });
  if (!rgb) {
    let lo = 0;
    let hi = color.c;
    rgb = oklchToLinearRgb({ l, c: 0, h: color.h }) as [number, number, number];
    for (let i = 0; i < 24; i++) {
      const mid = (lo + hi) / 2;
      const fit = oklchToLinearRgb({ l, c: mid, h: color.h });
      if (fit) {
        rgb = fit;
        lo = mid;
      } else {
        hi = mid;
      }
    }
  }
  return "#" + rgb.map((v) => Math.round(clamp01(linearToSrgb(clamp01(v))) * 255).toString(16).padStart(2, "0")).join("");
}

/** Black or white, whichever reads better on `bg`, with its ratio. */
export function bestOnColor(bg: string): { color: "#000000" | "#ffffff"; ratio: number } {
  const lum = relativeLuminance(bg);
  const white = contrastRatio(lum, 1);
  const black = contrastRatio(lum, 0);
  return white > black ? { color: "#ffffff", ratio: white } : { color: "#000000", ratio: black };
}

export interface Surface {
  /** The background actually applied: the picked color unless it had to be adjusted. */
  surface: string;
  onSurface: string;
  ratio: number;
  /** True when the picked color could not reach the target and its lightness was moved. */
  adjusted: boolean;
}

/**
 * Resolve the picked main color against a contrast target. When black or white text already meets
 * `target` the color is used as-is. Otherwise lightness (hue and chroma kept) moves away from the
 * text color, in steps of 0.01, until `target` is met.
 */
export function resolveSurface(primary: string, target: number = DEFAULT_CONTRAST): Surface {
  const first = bestOnColor(primary);
  if (first.ratio >= target) {
    return { surface: primary, onSurface: first.color, ratio: first.ratio, adjusted: false };
  }
  const origin = hexToOklch(primary);
  const step = first.color === "#ffffff" ? -0.01 : 0.01;
  let current = primary;
  let best = first;
  for (let l = origin.l + step; l >= 0 && l <= 1; l += step) {
    current = oklchToHex({ ...origin, l });
    best = bestOnColor(current);
    if (best.ratio >= target) break;
  }
  return { surface: current, onSurface: best.color, ratio: best.ratio, adjusted: true };
}

const MIN_ACCENT_CHROMA = 0.08;
const MAX_ACCENT_CHROMA = 0.15;

/** Hex at the given hue and chroma whose WCAG luminance matches `targetLuminance` (bisection on OKLCH L). */
function colorAtLuminance(hue: number, chroma: number, targetLuminance: number): string {
  let lo = 0;
  let hi = 1;
  let best = oklchToHex({ l: 0.5, c: chroma, h: hue });
  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2;
    const hex = oklchToHex({ l: mid, c: chroma, h: hue });
    const lum = relativeLuminance(hex);
    best = hex;
    if (Math.abs(lum - targetLuminance) < 0.0005) break;
    if (lum < targetLuminance) lo = mid;
    else hi = mid;
  }
  return best;
}

/**
 * `count` colors in total: slot 0 is `surface`, the others rotate the hue evenly around the wheel at
 * the same WCAG luminance, so one text color keeps the same contrast on every slot.
 */
export function generateAccents(surface: string, count: number): string[] {
  const total = Math.max(1, Math.floor(count));
  const base = hexToOklch(surface);
  const chroma = Math.min(MAX_ACCENT_CHROMA, Math.max(MIN_ACCENT_CHROMA, base.c));
  const luminance = relativeLuminance(surface);
  const accents = [surface];
  for (let i = 1; i < total; i++) {
    accents.push(colorAtLuminance((base.h + (360 / total) * i) % 360, chroma, luminance));
  }
  return accents;
}

// Theme tokens, for components that must look right in apps that do not load theme.css (chat and work use
// ChatWork's CSS). Two names only: --line (black or white) and --solid-0 (the page color); the softer shades of
// the line color are mixes of it. Where the token is missing a neutral default applies.

const SOLID = "var(--solid-0, #ffffff)";
export const LINE = "var(--line, #16181d)";
export const LINE_SOFT = "color-mix(in srgb, var(--line, #16181d) 30%, transparent)";
const SURFACE_TINT = "color-mix(in srgb, var(--line, #16181d) 8%, transparent)";

// Names the components import; each is one of the two tokens above, or a shade of the line color.
export const BG = SOLID;
export const FG = LINE;
export const BORDER = LINE_SOFT;
export const SURFACE = SURFACE_TINT;

// The glow of panels and cards: a soft shadow in the line color (same color as the border).

// One main color in, the whole token set of theme.css out. Pure functions plus thin storage helpers,
// no React: the picker (compounds/SiteSettings.tsx) builds on this file.

export interface ThemeConfig {
  /** The main color as the user picked it. */
  primary: string;
  /** Size of the accent palette, 1 to MAX_ACCENT_COUNT. */
  count: number;
  /** WCAG contrast target between the page color and its text. */
  contrast: ContrastLevel;
}

export type ThemeVars = Record<string, string>;

export const MAX_ACCENT_COUNT = 8;
export const DEFAULT_THEME: ThemeConfig = { primary: "#2f5fd0", count: 3, contrast: DEFAULT_CONTRAST };

/** Same origin for every app, so these keys are shared by all of them. */
export const THEME_STORAGE_KEY = "sn_theme";

export interface BuiltTheme {
  vars: ThemeVars;
  /** Contrast actually reached between page color and text. */
  ratio: number;
  /** True when the picked color had to be lightened or darkened to reach the target. */
  adjusted: boolean;
  accents: string[];
}

/** Every CSS variable a theme sets, with the values for `config`. */
export function buildTheme(config: ThemeConfig): BuiltTheme {
  const { surface, onSurface, ratio, adjusted } = resolveSurface(config.primary, config.contrast);
  const accents = generateAccents(surface, config.count);

  // Two names only. line-color: black or white, whichever contrasts more with the solid color; every stroke-like
  // property (color, border, outline, text-decoration, caret, column-rule, stroke, shadow, accent-color,
  // scrollbar…) reads --line. solid-color (background-color, fill): `count` colors with the same contrast against
  // --line; --solid-0 is the color that was picked.
  const vars: ThemeVars = { "--line": onSurface };
  for (let i = 0; i < MAX_ACCENT_COUNT; i++) vars[`--solid-${i}`] = accents[i % accents.length];
  return { vars, ratio, adjusted, accents };
}

/** Parse untrusted stored data into a valid config, or null. */
export function parseTheme(raw: unknown): ThemeConfig | null {
  if (!raw || typeof raw !== "object") return null;
  const { primary, count, contrast } = raw as Record<string, unknown>;
  if (!isHexColor(primary)) return null;
  const wholeCount = typeof count === "number" && Number.isInteger(count) ? count : DEFAULT_THEME.count;
  return {
    primary: primary.toLowerCase(),
    count: Math.min(MAX_ACCENT_COUNT, Math.max(1, wholeCount)),
    contrast: isContrastLevel(contrast) ? contrast : DEFAULT_CONTRAST,
  };
}

export function applyThemeVars(vars: ThemeVars, root: HTMLElement = document.documentElement): void {
  for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value);
}

export function clearThemeVars(vars: ThemeVars, root: HTMLElement = document.documentElement): void {
  for (const name of Object.keys(vars)) root.style.removeProperty(name);
}

export function loadTheme(storage: Pick<Storage, "getItem"> = localStorage): ThemeConfig | null {
  try {
    const raw = storage.getItem(THEME_STORAGE_KEY);
    return raw ? parseTheme(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}

/** Persist the config; ThemePicker rebuilds and applies the variables from it when a page mounts. */
export function saveTheme(config: ThemeConfig, storage: Pick<Storage, "setItem"> = localStorage): void {
  try {
    storage.setItem(THEME_STORAGE_KEY, JSON.stringify(config));
  } catch {
    // storage full or blocked: the theme still applies for this page view
  }
}

// Pure color math for the shared theme: OKLCH conversion, WCAG contrast and palette helpers.
// No React and no DOM, so every function is unit-testable and safe to import anywhere.
