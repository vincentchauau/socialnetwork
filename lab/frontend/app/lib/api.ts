import { apiFetch } from "@sn/api";

import type { LabStatus, LogLevel, LogRow, NotificationRow, ReplayResponse, UserLookup } from "./types";

export const LAB_API = "/api/lab";
export const NOTIFICATIONS_LIMIT = 20;
export const LOGS_LIMIT = 50;

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const labApi = {
  status: () => apiFetch<LabStatus>(`${LAB_API}/status`),
  lookup: (id: string) => apiFetch<UserLookup>(`${LAB_API}/users/${encodeURIComponent(id)}`),
  clearCache: (id: string) =>
    apiFetch<void>(`${LAB_API}/users/${encodeURIComponent(id)}/cache`, { method: "DELETE" }),
  notify: (title: string, body: string) =>
    apiFetch<{ id: string | number }>(`${LAB_API}/notifications`, post({ title, body })),
  notifications: () => apiFetch<NotificationRow[]>(`${LAB_API}/notifications?limit=${NOTIFICATIONS_LIMIT}`),
  log: (level: LogLevel, message: string) => apiFetch<unknown>(`${LAB_API}/logs`, post({ level, message })),
  logs: () => apiFetch<LogRow[]>(`${LAB_API}/logs?limit=${LOGS_LIMIT}`),
  replay: async (): Promise<LogRow[]> =>
    (await apiFetch<ReplayResponse>(`${LAB_API}/logs/replay?limit=${LOGS_LIMIT}`))?.messages ?? [],
  clearEvents: () => apiFetch<void>(`${LAB_API}/events`, { method: "DELETE" }),
};
