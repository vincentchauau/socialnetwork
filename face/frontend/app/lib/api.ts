import { apiFetch } from "@sn/api";

import type { Measurement, Scores } from "./types";

export const FACE_API = "/api/face";
export const HISTORY_LIMIT = 50;

export const faceApi = {
  save: (scores: Scores) =>
    apiFetch<Measurement>(`${FACE_API}/measurements`, { method: "POST", body: JSON.stringify(scores) }),
  list: (limit = HISTORY_LIMIT) => apiFetch<Measurement[]>(`${FACE_API}/measurements?limit=${limit}`),
  remove: (id: Measurement["id"]) =>
    apiFetch<void>(`${FACE_API}/measurements/${encodeURIComponent(String(id))}`, { method: "DELETE" }),
  removeAll: () => apiFetch<void>(`${FACE_API}/measurements`, { method: "DELETE" }),
};
