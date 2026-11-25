import { CENTER_API, apiFetch } from "@sn/api";

import type { Profile } from "./profile";

/** The CV as the server sends it: the profile, with the parts the viewer may not read left empty (`hidden`). */
export interface Cv extends Omit<Profile, "visibility"> {
  username: string | null;
  hidden: string[];
}

export function getCv(username: string): Promise<Cv> {
  return apiFetch<Cv>(`${CENTER_API}/auth/cv/${encodeURIComponent(username)}`);
}

