/** Palette picking for the Theme button: 9-shade ramps, CSS variables, contrast guard. */

export type Variant = "dark" | "light";

export interface ThemeTokens {
  bg: string;
  surface: string;
  fg: string;
  muted: string;
  border: string;
  accent: string;
  accent2: string;
  accentFg: string;
  danger: string;
}

export interface StoredTheme {
  palette: number;
  variant: Variant;
}

export const MIN_CONTRAST = 4.5;
export const THEME_STORAGE_KEY = "chat.theme";
export const SHADE_COUNT = 9;

/** Default: dark plum with light pink text and borders. */
export const DEFAULT_TOKENS: ThemeTokens = {
  bg: "#1f0016",
  surface: "#2c0a22",
  fg: "#ffd1ea",
  muted: "#f0a6cd",
  border: "#ff69b4",
  accent: "#ff9ccf",
  accent2: "#e0589f",
  accentFg: "#1f0016",
  danger: "#ffb3c0",
};

const LIGHTNESS = [8, 16, 24, 34, 46, 58, 70, 82, 94];
const SATURATION = 55;
const HUES = [330, 200, 150, 40, 270, 0, 100, 220, 20];

function hslToHex(hue: number, sat: number, light: number): string {
  const s = sat / 100;
  const l = light / 100;
  const a = s * Math.min(l, 1 - l);
  const channel = (n: number) => {
    const k = (n + hue / 30) % 12;
    const value = l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return Math.round(value * 255)
      .toString(16)
      .padStart(2, "0");
  };
  return `#${channel(0)}${channel(8)}${channel(4)}`;
}

/** Built-in palettes, each 9 shades from darkest to lightest. */
export const PALETTES: readonly (readonly string[])[] = HUES.map((hue) =>
  LIGHTNESS.map((light) => hslToHex(hue, SATURATION, light)),
);

export function buildTokens(palette: readonly string[], variant: Variant): ThemeTokens {
  const s = palette;
  return variant === "dark"
    ? {
        bg: s[0], surface: s[1], fg: s[8], muted: s[7], border: s[5],
        accent: s[8], accent2: s[6], accentFg: s[0], danger: "#ffb3c0",
      }
    : {
        bg: s[8], surface: s[7], fg: s[0], muted: s[1], border: s[3],
        accent: s[2], accent2: s[1], accentFg: s[8], danger: "#9c1c14",
      };
}

function luminance(hex: string): number {
  const value = /^#([0-9a-f]{6})$/i.exec(hex)?.[1];
  if (!value) return NaN;
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(value.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** Every text/background pair the UI uses must reach WCAG AA (4.5:1); NaN never passes. */
export function passesContrast(t: ThemeTokens): boolean {
  const pairs: [string, string][] = [
    [t.fg, t.bg],
    [t.fg, t.surface],
    [t.muted, t.bg],
    [t.muted, t.surface],
    [t.accent, t.bg],
    [t.danger, t.bg],
    [t.accentFg, t.accent],
    [t.accentFg, t.accent2],
  ];
  return pairs.every(([x, y]) => contrastRatio(x, y) >= MIN_CONTRAST);
}

export interface Pick extends StoredTheme {
  tokens: ThemeTokens;
}

/** Random palette and variant; combinations below AA are skipped, null when none is left. */
export function pickTheme(
  palettes: readonly (readonly string[])[] = PALETTES,
  random: () => number = Math.random,
): Pick | null {
  const candidates: StoredTheme[] = palettes.flatMap((shades, palette) =>
    shades.length === SHADE_COUNT
      ? (["dark", "light"] as const).map((variant) => ({ palette, variant }))
      : [],
  );
  while (candidates.length > 0) {
    const index = Math.min(candidates.length - 1, Math.floor(random() * candidates.length));
    const [choice] = candidates.splice(index, 1);
    const tokens = buildTokens(palettes[choice.palette], choice.variant);
    if (passesContrast(tokens)) return { ...choice, tokens };
  }
  return null;
}

const CSS_VARS: Record<keyof ThemeTokens, string> = {
  bg: "--bg", surface: "--surface", fg: "--fg", muted: "--muted", border: "--border",
  accent: "--accent", accent2: "--accent-2", accentFg: "--accent-fg", danger: "--danger",
};

export function applyTokens(tokens: ThemeTokens, root: HTMLElement = document.documentElement): void {
  for (const key of Object.keys(CSS_VARS) as (keyof ThemeTokens)[]) {
    root.style.setProperty(CSS_VARS[key], tokens[key]);
  }
}

export function readStoredTheme(): Pick | null {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (!raw) return null;
    const data: unknown = JSON.parse(raw);
    if (typeof data !== "object" || data === null) return null;
    const { palette, variant } = data as Record<string, unknown>;
    if (variant !== "dark" && variant !== "light") return null;
    if (typeof palette !== "number" || !Number.isInteger(palette)) return null;
    const shades = PALETTES[palette];
    if (!shades) return null;
    const tokens = buildTokens(shades, variant);
    return passesContrast(tokens) ? { palette, variant, tokens } : null;
  } catch {
    return null; // storage blocked or corrupt: fall back to the default theme
  }
}

export function writeStoredTheme(choice: StoredTheme): void {
  try {
    window.localStorage.setItem(
      THEME_STORAGE_KEY,
      JSON.stringify({ palette: choice.palette, variant: choice.variant }),
    );
  } catch {
    // storage blocked or full: the choice just lasts for this page view
  }
}

/** Pick, apply and remember a new theme; false when no palette passes the contrast guard. */
export function shuffleTheme(palettes: readonly (readonly string[])[] = PALETTES): boolean {
  const choice = pickTheme(palettes);
  if (!choice) return false;
  applyTokens(choice.tokens);
  writeStoredTheme(choice);
  return true;
}
