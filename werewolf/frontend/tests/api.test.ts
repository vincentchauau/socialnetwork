import { beforeEach, describe, expect, it, vi } from "vitest";

import { werewolfApi } from "../app/lib/api";

const fetchMock = vi.fn();

function ok(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(() => ok({}));
  vi.stubGlobal("fetch", fetchMock);
});

function lastCall(): { path: string; init: RequestInit } {
  const [path, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
  return { path, init };
}

describe("werewolfApi", () => {
  it("reads with GET and cookies", async () => {
    await werewolfApi.meta();
    expect(lastCall().path).toBe("/api/werewolf/setup/meta");
    expect(lastCall().init.credentials).toBe("include");
    await werewolfApi.random(12);
    expect(lastCall().path).toBe("/api/werewolf/setup/random?count=12");
    await werewolfApi.rooms();
    expect(lastCall().path).toBe("/api/werewolf/rooms");
    await werewolfApi.room("ABCDE");
    expect(lastCall().path).toBe("/api/werewolf/rooms/ABCDE");
    await werewolfApi.perspective("ABCDE", 3);
    expect(lastCall().path).toBe("/api/werewolf/rooms/ABCDE/perspective/3");
    await werewolfApi.history();
    expect(lastCall().path).toBe("/api/werewolf/me/history?limit=50");
    await werewolfApi.history(5);
    expect(lastCall().path).toBe("/api/werewolf/me/history?limit=5");
  });

  it("posts room commands with the documented bodies", async () => {
    await werewolfApi.create({ count: 5, start: true });
    expect(lastCall().path).toBe("/api/werewolf/rooms");
    expect(lastCall().init.method).toBe("POST");
    expect(JSON.parse(String(lastCall().init.body))).toEqual({ count: 5, start: true });

    await werewolfApi.join("ABCDE");
    expect(lastCall().path).toBe("/api/werewolf/rooms/ABCDE/join");
    expect(lastCall().init.body).toBeUndefined();

    await werewolfApi.addBots("ABCDE", 3);
    expect(JSON.parse(String(lastCall().init.body))).toEqual({ count: 3 });

    await werewolfApi.act("ABCDE", 4, "wolf");
    expect(lastCall().path).toBe("/api/werewolf/rooms/ABCDE/action");
    expect(JSON.parse(String(lastCall().init.body))).toEqual({ target: 4, kind: "wolf" });

    await werewolfApi.chat("ABCDE", "hi", 2);
    expect(JSON.parse(String(lastCall().init.body))).toEqual({ text: "hi", target: 2 });

    for (const [call, suffix] of [
      [werewolfApi.leave, "leave"],
      [werewolfApi.start, "start"],
      [werewolfApi.force, "force"],
      [werewolfApi.rematch, "rematch"],
      [werewolfApi.reset, "reset"],
    ] as const) {
      await call("ABCDE");
      expect(lastCall().path).toBe(`/api/werewolf/rooms/ABCDE/${suffix}`);
      expect(lastCall().init.method).toBe("POST");
    }
  });
});
