import { describe, expect, it } from "vitest";

import {
  backoffDelay,
  buildTimeline,
  describeClose,
  isValidRoom,
  mergeMessages,
  parseFrame,
  parseHistory,
  parseRooms,
  socketUrl,
  systemText,
  translateServerError,
} from "../app/protocol";

const m = (id: number, created_at = "2026-01-01T00:00:00Z") => ({
  id,
  room: "g",
  username: "a",
  content: "x",
  created_at,
});

describe("room name validation", () => {
  it.each(["general", "a", "A_b-9", "x".repeat(32)])("accepts %s", (name) => {
    expect(isValidRoom(name)).toBe(true);
  });
  it.each(["", "x".repeat(33), "a b", "a/b", "tiếng", "a\n"])("rejects %j", (name) => {
    expect(isValidRoom(name)).toBe(false);
  });
});

describe("parseFrame", () => {
  it("parses every known frame type", () => {
    expect(parseFrame(JSON.stringify({ type: "message", ...m(1) }))).toEqual({
      type: "message",
      message: m(1),
    });
    expect(
      parseFrame('{"type":"system","event":"join","room":"g","userId":2,"username":"bob","at":"t"}'),
    ).toEqual({ type: "system", event: "join", username: "bob", at: "t" });
    expect(
      parseFrame('{"type":"presence","members":[{"userId":1,"username":"a"}],"total":3}'),
    ).toEqual({ type: "presence", members: [{ userId: 1, username: "a" }], total: 3 });
    expect(parseFrame('{"type":"error","error":"boom"}')).toEqual({ type: "error", error: "boom" });
    expect(parseFrame('{"type":"rooms","rooms":[{"room":"g","users":2}]}')).toEqual({
      type: "rooms",
      rooms: [{ room: "g", users: 2 }],
    });
  });

  it.each([
    42,
    "not json",
    "null",
    "[]",
    '{"type":"nope"}',
    '{"type":"message","id":"1"}',
    '{"type":"system","event":"kick","username":"a","at":"t"}',
    '{"type":"system","event":"join","username":1,"at":"t"}',
    '{"type":"presence","members":"x","total":1}',
    '{"type":"presence","members":[{"userId":"1","username":"a"}],"total":1}',
    '{"type":"presence","members":[],"total":"1"}',
    '{"type":"error","error":5}',
    '{"type":"rooms","rooms":[{"room":1,"users":1}]}',
    '{"type":"rooms","rooms":null}',
  ])("ignores malformed frame %j", (raw) => {
    expect(parseFrame(raw)).toBeNull();
  });
});

describe("REST payloads", () => {
  it("keeps only well-formed history rows", () => {
    expect(parseHistory([m(1), { id: 2 }, null, 5])).toEqual([m(1)]);
    expect(parseHistory({})).toEqual([]);
  });
  it("parses rooms and tolerates garbage", () => {
    expect(parseRooms([{ room: "g", users: 1 }])).toEqual([{ room: "g", users: 1 }]);
    expect(parseRooms([{ room: "g" }])).toEqual([]);
    expect(parseRooms("x")).toEqual([]);
  });
});

describe("mergeMessages / buildTimeline", () => {
  it("dedupes by id, sorts by id and prefers later lists", () => {
    const newer = { ...m(2), content: "new" };
    expect(mergeMessages([m(3), m(2)], [newer, m(1)]).map((x) => [x.id, x.content])).toEqual([
      [1, "x"],
      [2, "new"],
      [3, "x"],
    ]);
  });

  it("orders messages and system lines chronologically, bad dates first", () => {
    const items = buildTimeline(
      [m(1, "2026-01-01T00:00:10Z")],
      [
        { key: "s1", event: "join", username: "b", at: "2026-01-01T00:00:05Z" },
        { key: "s2", event: "leave", username: "b", at: "garbage" },
      ],
    );
    expect(items.map((i) => i.key)).toEqual(["s2", "s1", "m1"]);
  });
});

describe("texts and helpers", () => {
  it("formats system lines in Vietnamese", () => {
    expect(systemText({ event: "join", username: "An" })).toBe("An đã vào phòng");
    expect(systemText({ event: "leave", username: "An" })).toBe("An đã rời phòng");
  });

  it("translates known server errors only", () => {
    expect(translateServerError("Message must be 1-2000 characters")).toContain("2000");
    expect(translateServerError("Only text frames are supported")).toContain("văn bản");
    expect(translateServerError("other")).toBe("other");
  });

  it("maps close codes to actions and Vietnamese reasons", () => {
    expect(describeClose(1008, "").action).toBe("session");
    expect(describeClose(1013, "Room is full")).toEqual({ action: "stop", message: "Phòng đã đầy" });
    expect(describeClose(1013, "Too many active rooms").message).toBe(
      "Quá nhiều phòng đang hoạt động",
    );
    expect(describeClose(1013, "Too many connections").message).toBe("Bạn mở quá nhiều kết nối");
    expect(describeClose(1013, "???").message).toContain("bận");
    expect(describeClose(1009, "").action).toBe("retry");
    expect(describeClose(1009, "").message).toContain("quá lớn");
    expect(describeClose(1006, "")).toEqual({ action: "retry", message: null });
  });

  it("backs off exponentially up to 15 s", () => {
    expect([0, 1, 2, 3, 4, 5, 10].map(backoffDelay)).toEqual([
      1000, 1000, 2000, 4000, 8000, 15000, 15000,
    ]);
  });

  it("builds ws/wss urls from the page location", () => {
    expect(socketUrl("/ws/g")).toBe(`ws://${window.location.host}/api/chat/ws/g`);
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { protocol: "https:", host: "x.test" },
    });
    expect(socketUrl("/ws-lobby")).toBe("wss://x.test/api/chat/ws-lobby");
    Object.defineProperty(window, "location", { configurable: true, value: original });
  });
});
