import { ApiError, apiFetch } from "@sn/api";
import { vi } from "vitest";

import type { LabStatus, LogRow, NotificationRow } from "../app/lib/types";

export const ALL_UP: LabStatus = { redis: true, grpc: true, rabbitmq: true, kafka: true, messaging: true };
export const MESSAGING_OFF: LabStatus = { ...ALL_UP, rabbitmq: false, kafka: false, messaging: false };

export type Handler = unknown | ((init?: RequestInit) => unknown);
export type Routes = Record<string, Handler>;

export const apiError = (status: number, detail = "lỗi") => new ApiError(status, detail, { detail });

/** Routes "METHOD /path" (query string ignored) to a value, a thrown Error, or a function of the init. */
export function mockRoutes(routes: Routes) {
  const calls: string[] = [];
  vi.mocked(apiFetch).mockImplementation(async (path: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${path.split("?")[0]}`;
    calls.push(key);
    if (!(key in routes)) throw apiError(404, `no route ${key}`);
    const handler = routes[key];
    const value = typeof handler === "function" ? (handler as (i?: RequestInit) => unknown)(init) : handler;
    if (value instanceof Error) throw value;
    return value as never;
  });
  return calls;
}

export const countCalls = (calls: string[], key: string) => calls.filter((c) => c === key).length;

export const note = (over: Partial<NotificationRow> = {}): NotificationRow => ({
  id: 1, title: "Xin chào", status: "done", attempts: 1, ...over,
});

export const logRow = (over: Partial<LogRow> = {}): LogRow => ({
  level: "info", message: "khởi động", partition: 0, offset: 0, ...over,
});
