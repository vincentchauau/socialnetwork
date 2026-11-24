import { apiFetch } from "@sn/api";

import type { Measurement, Scores } from "./types";

const FACE_API = "/api/face";
const HISTORY_LIMIT = 50;

export const faceApi = {
  save: (scores: Scores) =>
    apiFetch<Measurement>(`${FACE_API}/measurements`, { method: "POST", body: JSON.stringify(scores) }),
  list: (limit = HISTORY_LIMIT) => apiFetch<Measurement[]>(`${FACE_API}/measurements?limit=${limit}`),
  remove: (id: Measurement["id"]) =>
    apiFetch<void>(`${FACE_API}/measurements/${encodeURIComponent(String(id))}`, { method: "DELETE" }),
  annotate: (id: Measurement["id"], note: string) =>
    apiFetch<Measurement>(`${FACE_API}/measurements/${encodeURIComponent(String(id))}`, { method: "PATCH", body: JSON.stringify({ note }) }),
  removeAll: () => apiFetch<void>(`${FACE_API}/measurements`, { method: "DELETE" }),
};
