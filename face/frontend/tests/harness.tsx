import { apiFetch } from "@sn/api";
import { act } from "@testing-library/react";
import { vi } from "vitest";

import type { FaceDeps, Landmarker } from "../app/lib/mediapipe";
import type { Landmark, Measurement, Scores } from "../app/lib/types";
import { buildFace, fakeContext } from "./helpers";

export const rafQueue: FrameRequestCallback[] = [];
export const ctx = fakeContext();

/** Camera/model fakes plus browser stubs (rAF, canvas, video) shared by the UI tests. */
export function installBrowserStubs() {
  rafQueue.length = 0;
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => rafQueue.push(cb));
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(ctx as never);
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  Object.defineProperty(HTMLMediaElement.prototype, "readyState", { configurable: true, get: () => 4 });
  Object.defineProperty(HTMLVideoElement.prototype, "videoWidth", { configurable: true, get: () => 640 });
  Object.defineProperty(HTMLVideoElement.prototype, "videoHeight", { configurable: true, get: () => 480 });
  for (const fn of Object.values(ctx)) if (vi.isMockFunction(fn)) fn.mockClear();
}

export function makeDeps(frames: (Landmark[] | null)[] = [buildFace()]) {
  const stop = vi.fn();
  const stream = { getTracks: () => [{ stop }, { stop }] } as unknown as MediaStream;
  let i = 0;
  const landmarker = {
    detect: vi.fn<Landmarker["detect"]>(async () => frames[Math.min(i++, frames.length - 1)]),
    close: vi.fn<Landmarker["close"]>(),
  };
  const deps = {
    openCamera: vi.fn<FaceDeps["openCamera"]>(async () => stream),
    createLandmarker: vi.fn<FaceDeps["createLandmarker"]>(async () => landmarker),
  };
  return { deps, stop, stream, landmarker };
}

/** Runs n animation frames, letting the async detect() settle after each. */
export async function pump(n = 1) {
  for (let k = 0; k < n; k++) {
    await act(async () => {
      rafQueue.shift()?.(0);
      for (let m = 0; m < 5; m++) await Promise.resolve();
    });
  }
}

export const saved = (over: Partial<Measurement> = {}): Measurement => ({
  id: 1, createdAt: "2026-01-02T03:04:05Z", symmetry: 90, eye: 95, nose: 96, mouth: 97, ear: null, angle: 89.5, ...over,
});

/** Routes apiFetch by method and path to an in-memory measurement list. */
export function mockBackend(initial: Measurement[] = []) {
  let rows = [...initial];
  let nextId = 100;
  const fetchMock = vi.mocked(apiFetch);
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (method === "GET") return [...rows] as never;
    if (method === "POST") {
      const row = { id: nextId++, createdAt: "2026-02-03T04:05:06Z", ...(JSON.parse(String(init?.body)) as Scores) };
      rows = [row, ...rows];
      return row as never;
    }
    const id = path.split("/").pop();
    rows = id === "measurements" ? [] : rows.filter((r) => String(r.id) !== id);
    return undefined as never;
  });
  return fetchMock;
}
