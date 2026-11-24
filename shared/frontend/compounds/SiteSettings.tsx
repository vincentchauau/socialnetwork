"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Button from "../elements/Button";
import Card from "../elements/Card";
import TextBox from "../elements/TextBox";
import { BG, FG } from "../lib/theme";
import { useLocale } from "../lib/i18n";
import Select from "../elements/Select";

import {
  DEFAULT_THEME,
  MAX_ACCENT_COUNT,
  THEME_STORAGE_KEY,
  type ThemeConfig,
  applyThemeVars,
  buildTheme,
  clearThemeVars,
  loadTheme,
  saveTheme,
} from "../lib/theme";

export interface ThemeLabels {
  theme: string;
  color: string;
  count: string;
}

const DEFAULT_LABELS: ThemeLabels = {
  theme: "Theme",
  color: "Main color",
  count: "Accent colors",
};

// A label with its control on the right; inline, so it works in apps that do not load theme.css.
const ROW = { display: "flex", alignItems: "center", gap: 8 } as const;

// Every theme sets the same variable names, so the defaults tell us what to remove on reset.
const THEME_VAR_NAMES = Object.keys(buildTheme(DEFAULT_THEME).vars);

function removeThemeVars(): void {
  clearThemeVars(Object.fromEntries(THEME_VAR_NAMES.map((name) => [name, ""])));
}

/**
 * Floating theme control shared by every app. The main color comes from a color picker; the accent
 * count and a WCAG contrast level shape the rest. Until the user picks something, theme.css keeps
 * following the system light or dark setting.
 */
export function ThemePicker({
  labels,
  inline = false,
  expanded = false,
}: {
  labels?: Partial<ThemeLabels>;
  inline?: boolean;
  /** Show the controls directly, with no button to open them: for a menu that is itself opened and closed. */
  expanded?: boolean;
}) {
  const text = { ...DEFAULT_LABELS, ...labels };
  const [config, setConfig] = useState<ThemeConfig>(DEFAULT_THEME);
  const [active, setActive] = useState(false);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const built = useMemo(() => buildTheme(config), [config]);

  useEffect(() => {
    const saved = loadTheme();
    if (saved) {
      setConfig(saved);
      setActive(true);
    }
  }, []);

  useEffect(() => {
    if (!active) return;
    applyThemeVars(built.vars);
    saveTheme(config);
  }, [active, built, config]);

  // Another tab or app on the same origin changed (or reset) the theme.
  useEffect(() => {
    function onStorage(event: StorageEvent) {
      if (event.key !== THEME_STORAGE_KEY) return;
      const saved = loadTheme();
      if (saved) {
        setConfig(saved);
        setActive(true);
      } else {
        removeThemeVars();
        setActive(false);
      }
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function update(patch: Partial<ThemeConfig>) {
    setConfig((prev) => ({ ...prev, ...patch }));
    setActive(true);
  }

  function changeCount(value: string) {
    const next = Number.parseInt(value, 10);
    if (Number.isNaN(next)) return;
    update({ count: Math.min(MAX_ACCENT_COUNT, Math.max(1, next)) });
  }

  const controls = (
    <>
      <label style={ROW}>
        {text.color}
        <TextBox
          type="color"
          aria-label={text.color}
          value={config.primary}
          onChange={(event) => update({ primary: event.target.value })}
          style={{ flex: "none", width: 56, height: 36, padding: 2 }}
        />
      </label>
      <label style={ROW}>
        {text.count}
        <TextBox
          type="number"
          aria-label={text.count}
          min={1}
          max={MAX_ACCENT_COUNT}
          value={config.count}
          onChange={(event) => changeCount(event.target.value)}
          style={{ flex: "none", width: 64 }}
        />
      </label>
      <div aria-hidden="true" style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {built.accents.map((color, index) => (
          <span key={index} style={{ width: 28, height: 28, borderRadius: 6, background: color, border: "1px solid color-mix(in srgb, var(--line, currentColor) 30%, transparent)" }} />
        ))}
      </div>
    </>
  );

  if (expanded) {
    return (
      <div role="group" aria-label={text.theme} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 16 }}>
        {controls}
      </div>
    );
  }

  return (
    <div ref={rootRef} style={inline ? { position: "relative" } : { position: "fixed", top: 8, right: 8, zIndex: 50 }}>
      <Button type="button" variant="secondary" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {text.theme}
      </Button>
      {open && (
        <Card
          role="dialog"
          aria-label={text.theme}
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            gap: 16,
            width: "max-content",
            maxWidth: "min(92vw, 760px)",
            marginTop: 8,
            background: BG,
            color: FG,
            ...(inline ? { position: "absolute", right: 0, top: "100%", zIndex: 50 } : {}),
          }}
        >
          {controls}
        </Card>
      )}
    </div>
  );
}

export default ThemePicker;

const RTL_LOCALES = new Set(["ar", "he", "fa", "ur"]);

export interface LanguageSwitcherProps {
  /** Locale codes to offer, e.g. ["vi", "en"]. */
  locales: string[];
  /** Controlled value; defaults to the locale from LocaleProvider. */
  value?: string;
  onChange?: (locale: string) => void;
  label?: string;
  /** Display names, e.g. { vi: "Tiếng Việt" }; a code without a name shows the code. */
  names?: Record<string, string>;
}

/** Select that sets <html lang/dir> and the shared locale; the option list itself is rendered by the OS. */
export function LanguageSwitcher({ locales, value, onChange, label = "Select language", names = {} }: LanguageSwitcherProps) {
  const { locale, setLocale } = useLocale();

  function change(next: string) {
    document.documentElement.lang = next;
    document.documentElement.dir = RTL_LOCALES.has(next) ? "rtl" : "ltr";
    setLocale(next);
    onChange?.(next);
  }

  return (
    <Select aria-label={label} value={value ?? locale} onChange={(event) => change(event.target.value)}>
      {locales.map((code) => (
        <option key={code} value={code}>
          {names[code] ?? code}
        </option>
      ))}
    </Select>
  );
}
