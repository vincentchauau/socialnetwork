import type { ComponentType } from "react";
import dynamic from "next/dynamic";

/**
 * The library (gallery) of each app, by API module name: a component with no props that renders only the gallery content.
 * Loaded lazily so the dock never imports the pages of the apps. To add one: create `app/<app>/<Name>Library.tsx` and add a line here.
 * Each entry includes the home pathname where the library fills the entire page.
 */
const LIBRARIES: Record<string, { component: ComponentType; home: string }> = {
  file: { component: dynamic(() => import("../../file/FileLibrary")), home: "/file" },
  face: { component: dynamic(() => import("../../face/FaceLibrary")), home: "/face" },
  job: { component: dynamic(() => import("../../job/JobLibrary")), home: "/job" },
  market: { component: dynamic(() => import("../../market/MarketLibrary")), home: "/market" },
};

/** The library component of an app's API module, or undefined when it has none. */
export function libraryOf(api: string): ComponentType | undefined {
  const entry = Object.prototype.hasOwnProperty.call(LIBRARIES, api) ? LIBRARIES[api] : undefined;
  return entry?.component;
}

/** The home pathname of an app's library, or undefined when it has none. */
export function libraryEntryOf(api: string): { component: ComponentType; home: string } | undefined {
  return Object.prototype.hasOwnProperty.call(LIBRARIES, api) ? LIBRARIES[api] : undefined;
}

/** Check if the given pathname is the home page of a library. Trailing-slash tolerant. */
export function isLibraryHome(pathname: string, home: string): boolean {
  if (!home) return false;
  const normalized = pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
  const normalizedHome = home.endsWith("/") ? home.slice(0, -1) : home;
  return normalized === normalizedHome;
}
