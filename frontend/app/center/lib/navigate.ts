import { safeNextPath } from "./auth";

export function goTo(path: string): void {
  window.location.assign(path);
}

/** Where to go after signing in: the validated `next` query parameter, else the home page. */
export function postLoginTarget(): string {
  return safeNextPath(new URLSearchParams(window.location.search).get("next"));
}
