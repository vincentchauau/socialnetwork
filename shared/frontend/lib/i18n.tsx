"use client";

import { Fragment, type ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/** Nested string bundle, e.g. { common: { save: "Lưu" } } is read with the path "common.save". */
export interface Bundle {
  [key: string]: string | Bundle;
}

/** Same origin for every app, so a choice made in one app reaches the others through the storage event. */
export const LOCALE_STORAGE_KEY = "sn_locale";
const DEFAULT_LOCALE = "vi";

export interface LocaleContextValue {
  locale: string;
  setLocale: (locale: string) => void;
  /** True inside a LocaleProvider: a provider within another one adds nothing, so a page has one state. */
  provided?: boolean;
}

/**
 * `tr("key")` for code that is not a hook (constants, helpers, error texts): the text of the locale being shown, from the
 * bundles an app registered with `registerBundles` ({ vi: { key: "..." }, en: { key: "..." } }); a key missing in the
 * locale falls back to Vietnamese, then to the key itself. `{name}` in a text is filled from `params`. The page below a
 * LocaleProvider is remounted when the locale changes, so every `tr` call runs again.
 */
let shown = DEFAULT_LOCALE;
const registry: Record<string, Record<string, string>> = {};

/** Texts a server sends in Vietnamese, with their English: whole texts, and patterns for texts with names or numbers in them. */
export interface ServerTexts {
  exact?: Record<string, string>;
  patterns?: string[][];
}

const serverExact: Record<string, string> = {};
const serverPatterns: [RegExp, string][] = [];

/** The locale to hand to Intl / toLocale*String for the language the site is showing. */
export function intlLocale(): string {
  return shown === "en" ? "en-US" : "vi-VN";
}

export function registerBundles(bundles: Record<string, Record<string, string> | ServerTexts>): void {
  for (const [locale, texts] of Object.entries(bundles)) {
    if (locale === "server") {
      const server = texts as ServerTexts;
      Object.assign(serverExact, server.exact);
      for (const [source, english] of server.patterns ?? []) serverPatterns.push([new RegExp(source), english]);
    } else {
      registry[locale] = { ...registry[locale], ...(texts as Record<string, string>) };
    }
  }
}

/**
 * The texts of ONE app when several apps live in one bundle: every key is kept under `<prefix>:`, so two apps can use the
 * same key for different texts. Returns the `tr` of that app (a key it does not know falls back to Vietnamese, then to the key).
 */
export function registerScoped(prefix: string, bundles: Record<string, Record<string, string> | ServerTexts>) {
  const scoped: Record<string, Record<string, string> | ServerTexts> = {};
  for (const [locale, texts] of Object.entries(bundles)) {
    scoped[locale] =
      locale === "server"
        ? texts
        : Object.fromEntries(Object.entries(texts as Record<string, string>).map(([key, text]) => [`${prefix}:${key}`, text]));
  }
  registerBundles(scoped);
  return (key: string, params?: Record<string, string | number>): string => {
    const text = tr(`${prefix}:${key}`, params);
    return text.startsWith(`${prefix}:`) && text === `${prefix}:${key}` ? key : text;
  };
}

/**
 * A text the server wrote in Vietnamese, in the locale being shown: the English of a known text or pattern (the parts a
 * pattern captures are translated too, so names stay as they are and "Sói" becomes "Wolf"); any other text as it is.
 */
export function trServer(text: string, depth = 0): string {
  if (shown === DEFAULT_LOCALE || depth > 3) return text;
  const exact = serverExact[text];
  if (exact !== undefined) return exact;
  for (const [pattern, english] of serverPatterns) {
    const match = pattern.exec(text);
    if (match) return english.replace(/\{(\d+)\}/g, (_, index: string) => trServer(match[Number(index)] ?? "", depth + 1));
  }
  return text;
}

/** `trServer` on every string of a parsed JSON value. */
export function trServerDeep<T>(value: T): T {
  if (shown === DEFAULT_LOCALE) return value;
  if (typeof value === "string") return trServer(value) as T;
  if (Array.isArray(value)) return value.map((item) => trServerDeep(item)) as T;
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, trServerDeep(item)])) as T;
  }
  return value;
}

/** The part of a "Tiếng Việt / English" text in the language being shown (a text without " / " is left as it is). */
export function pickLanguage(text: string): string {
  const at = text.indexOf(" / ");
  if (at < 0) return text;
  return shown === "en" ? text.slice(at + 3) : text.slice(0, at);
}

export function tr(key: string, params?: Record<string, string | number>): string {
  const text = registry[shown]?.[key] ?? registry[DEFAULT_LOCALE]?.[key] ?? key;
  return params ? text.replace(/\{(\w+)\}/g, (_, name: string) => String(params[name] ?? "")) : text;
}

const LocaleContext = createContext<LocaleContextValue>({ locale: DEFAULT_LOCALE, setLocale: () => {} });

function readStoredLocale(fallback: string): string {
  try {
    return window.localStorage.getItem(LOCALE_STORAGE_KEY) || fallback;
  } catch {
    return fallback;
  }
}

export function LocaleProvider({ children, defaultLocale = DEFAULT_LOCALE }: { children: ReactNode; defaultLocale?: string }) {
  const outer = useContext(LocaleContext);
  if (outer.provided) return <>{children}</>;
  return <OwnLocale defaultLocale={defaultLocale}>{children}</OwnLocale>;
}

function OwnLocale({ children, defaultLocale }: { children: ReactNode; defaultLocale: string }) {
  const [locale, setLocaleState] = useState(defaultLocale);

  useEffect(() => {
    setLocaleState(readStoredLocale(defaultLocale));
    function onStorage(event: StorageEvent) {
      if (event.key === LOCALE_STORAGE_KEY && event.newValue) setLocaleState(event.newValue);
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [defaultLocale]);

  const setLocale = useCallback((next: string) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      // storage blocked: the choice still applies to this page view
    }
  }, []);

  const value = useMemo(() => ({ locale, setLocale, provided: true }), [locale, setLocale]);
  shown = locale; // set while rendering, so the `tr` calls of the page below read this locale
  return (
    <LocaleContext.Provider value={value}>
      <Fragment key={locale}>{children}</Fragment>
    </LocaleContext.Provider>
  );
}

export function useLocale(): LocaleContextValue {
  return useContext(LocaleContext);
}

/** Look up a dot path in a bundle; a missing key returns the path itself so gaps are visible, not blank. */
export function translate(bundle: Bundle | undefined, path: string): string {
  let node: string | Bundle | undefined = bundle;
  for (const key of path.split(".")) {
    if (node === undefined || typeof node === "string") return path;
    node = node[key];
  }
  return typeof node === "string" ? node : path;
}

/** `t(path)` for the current locale; an unknown locale falls back to the first bundle. */
export function useTranslation(bundles: Record<string, Bundle>) {
  const { locale, setLocale } = useLocale();
  const bundle = bundles[locale] ?? Object.values(bundles)[0];
  const t = useCallback((path: string) => translate(bundle, path), [bundle]);
  return { t, locale, setLocale };
}
