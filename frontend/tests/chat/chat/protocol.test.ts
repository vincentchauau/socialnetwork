import { describe, expect, it } from "vitest";

import {
  type ChatMessage,
  backoffDelay,
  buildTimeline,
  describeClose,
  isOwner,
  mergeMessages,
  parseFrame,
  parseHistory,
  readHash,
  roomLink,
  stateText,
  systemText,
  translateServerError,
} from "../../../app/chat/protocol";

const message = (id: number, extra: Partial<ChatMessage> = {}): ChatMessage => ({
  id,
  user_id: 2,
  username: "bob",
  kind: "text",
  content: `m${id}`,
  reply_to_id: null,
  pinned_at: null,
  edited_at: null,
  created_at: `2026-01-01T00:00:${String(id).padStart(2, "0")}Z`,
  ...extra,
});

const raw = (value: unknown) => JSON.stringify(value);

describe("parseFrame", () => {
  it("reads a message with everything the server sends", () => {
    const frame = parseFrame(raw({ type: "message", ...message(1, { reply_to_id: 4, pinned_at: "2026-01-01T00:01:00Z" }) }));
    expect(frame).toEqual({ type: "message", message: message(1, { reply_to_id: 4, pinned_at: "2026-01-01T00:01:00Z" }) });
  });

  it("fills in what an older server leaves out", () => {
    const frame = parseFrame(raw({ type: "message", id: 1, username: "bob", content: "hi", created_at: "2026-01-01T00:00:00Z" }));
    expect(frame).toMatchObject({ type: "message", message: { user_id: 0, kind: "text", reply_to_id: null, pinned_at: null } });
  });

  it.each([
    [{ type: "message", id: "1", username: "b", content: "x", created_at: "t" }],
    [{ type: "system", event: "wave", username: "b", at: "t" }],
    [{ type: "presence", members: [{ userId: "1", username: "a" }], total: 1 }],
    [{ type: "presence", members: [], total: "1" }],
    [{ type: "error", error: 5 }],
    [{ type: "rooms", rooms: [{ room: 1, users: 1 }] }],
    [{ type: "rooms", rooms: [{ room: "g", users: 1, members: [1] }] }],
    [{ type: "deleted", id: "7" }],
    [{ type: "pinned", id: 7 }],
    [{ type: "member", event: "join", user_id: "1", username: "a" }],
    [{ type: "unknown" }],
    ["not json at all"],
  ])("refuses a malformed frame %#", (frame) => {
    expect(parseFrame(typeof frame === "string" ? frame : raw(frame))).toBeNull();
  });

  it("reads the other frames", () => {
    expect(parseFrame(raw({ type: "system", event: "join", username: "bob", at: "t" }))).toEqual({ type: "system", event: "join", username: "bob", at: "t" });
    expect(parseFrame(raw({ type: "presence", members: [{ userId: 1, username: "a" }], total: 3 }))).toEqual({ type: "presence", members: [{ userId: 1, username: "a" }], total: 3 });
    expect(parseFrame(raw({ type: "error", error: "x" }))).toEqual({ type: "error", error: "x" });
    expect(parseFrame(raw({ type: "rooms", rooms: [{ room: "g", users: 2, members: ["a", "b"] }], version: 4 }))).toEqual({ type: "rooms", rooms: [{ room: "g", users: 2, members: ["a", "b"] }], version: 4, people: 0, online: 0 });
    expect(parseFrame(raw({ type: "rooms", rooms: [], version: 1, people: 7, online: 3 }))).toEqual({ type: "rooms", rooms: [], version: 1, people: 7, online: 3 });
    expect(parseFrame(raw({ type: "rooms", rooms: [] }))).toEqual({ type: "rooms", rooms: [], version: 0, people: 0, online: 0 });
    expect(parseFrame(raw({ type: "deleted", id: 7 }))).toEqual({ type: "deleted", id: 7 });
    expect(parseFrame(raw({ type: "pinned", id: 7, pinned: true }))).toEqual({ type: "pinned", id: 7, pinned: true });
    expect(parseFrame(raw({ type: "member", event: "leave", user_id: 3, username: "c" }))).toEqual({ type: "member", event: "leave", userId: 3, username: "c" });
    expect(parseFrame(raw({ type: "room", room: "g" }))).toEqual({ type: "room" });
    expect(parseFrame(42)).toBeNull();
  });
});

describe("messages", () => {
  it("parses a history and drops the rows that are not messages", () => {
    expect(parseHistory([message(1), { id: 2 }, "x", null])).toEqual([message(1)]);
    expect(parseHistory("nope")).toEqual([]);
  });

  it("merges by id, newest data winning, in id order", () => {
    const merged = mergeMessages([message(3), message(1)], [message(2), message(3, { content: "edited" })]);
    expect(merged.map((m) => [m.id, m.content])).toEqual([[1, "m1"], [2, "m2"], [3, "edited"]]);
  });

  it("puts messages and system lines in time order", () => {
    const items = buildTimeline([message(1), message(3)], [{ key: "s1", event: "join", username: "ann", at: "2026-01-01T00:00:02Z" }]);
    expect(items.map((item) => item.key)).toEqual(["m1", "s1", "m3"]);
  });

  it("words the join and leave lines", () => {
    expect(systemText({ event: "join", username: "ann" })).toBe("ann đã trực tuyến");
    expect(systemText({ event: "leave", username: "ann" })).toBe("ann đã ngoại tuyến");
  });
});

describe("rooms", () => {
  it("says why a room is not open", () => {
    expect(stateText("open")).toBeNull();
    expect(stateText("closed")).toBe("Phòng đã đóng");
    expect(stateText("deleted")).toBe("Phòng đã xóa");
  });

  it("knows who owns a room", () => {
    const me = { role: "member", status: "joined", muted: false, unread: 0 } as const;
    expect(isOwner(me)).toBe(false);
    expect(isOwner({ ...me, role: "owner" })).toBe(true);
    expect(isOwner({ ...me, role: "owner", status: "banned" })).toBe(false);
    expect(isOwner(null)).toBe(false);
  });

  it("makes and reads the link of a room", () => {
    window.history.pushState({}, "", "/chat");
    expect(roomLink("q7 sale")).toBe(`${window.location.origin}/chat#room=q7%20sale`);
    expect(readHash("#room=q7%20sale")).toEqual({ room: "q7 sale" });
    expect(readHash("")).toEqual({ room: null });
  });
});

describe("closing a socket", () => {
  it("tells a shut door from an ended session", () => {
    expect(describeClose(1008, "")).toMatchObject({ action: "session" });
    expect(describeClose(1008, "You are banned from this room")).toEqual({ action: "removed", message: "Bạn đã bị cấm khỏi phòng này." });
    expect(describeClose(1008, "Waiting for approval").action).toBe("removed");
    expect(describeClose(1008, "Room deleted").action).toBe("removed");
  });

  it("stops on a refusal, retries on the rest", () => {
    expect(describeClose(1013, "Room is full")).toEqual({ action: "stop", message: "Phòng đã đầy" });
    expect(describeClose(1013, "?").action).toBe("stop");
    expect(describeClose(1009, "").action).toBe("retry");
    expect(describeClose(1006, "")).toEqual({ action: "retry", message: null });
  });

  it("backs off, to a limit", () => {
    expect([1, 2, 3, 4, 5, 6].map(backoffDelay)).toEqual([1000, 2000, 4000, 8000, 15000, 15000]);
    expect(backoffDelay(0)).toBe(1000);
  });

  it("words the rules the server enforces", () => {
    expect(translateServerError("You are muted")).toBe("Bạn đang bị tắt tiếng trong phòng này.");
    expect(translateServerError("Only text frames are supported")).toBe("Chỉ hỗ trợ tin nhắn dạng văn bản.");
    expect(translateServerError("something else")).toBe("something else");
  });
});

describe("the line of the room about virtual people", () => {
  it("says who added how many, in one line", async () => {
    const { changeText } = await import("../../../app/chat/protocol");
    expect(changeText("virtual_added:3:alice")).toBe("alice đã thêm 3 người ảo vào phòng");
    expect(changeText("joined:ann")).toBe("ann đã tham gia phòng");
    expect(changeText("something else")).toBe("something else");
    expect(changeText("meeting:both")).toBe("Cuộc họp đã bắt đầu");
    expect(changeText("meeting:call")).toBe("Cuộc họp đã bắt đầu");
    expect(changeText("call:ann")).toBe("ann đã bắt đầu cuộc gọi video");
    expect(changeText("screen:ann")).toBe("ann đã bắt đầu chia sẻ màn hình");
  });
  it("words the end of a game of the room, with the side that won", async () => {
    const { changeText } = await import("../../../app/chat/protocol");
    expect(changeText("game_over:WOLF:4")).toBe("Ván Ma Sói kết thúc: phe Sói thắng sau 4 ngày");
    expect(changeText("game_over:DRAW:2")).toBe("Ván Ma Sói kết thúc: hòa sau 2 ngày");
    expect(changeText("ai_usage:120:15:1840:Giang Le")).toBe("Giang Le trả lời trong 1.8 giây · 120 token vào, 15 token ra");
  });
});
