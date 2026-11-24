import { ApiError } from "@sn/api";
import { describe, expect, it } from "vitest";

import { errorText, frameErrorText } from "../../app/werewolf/lib/errors";
import { groupLog } from "../../app/werewolf/lib/log";
import {
  MAX_RETRY_DELAY_MS,
  parseFrame,
  retryDelay,
  sanitizeRoom,
  socketUrl,
} from "../../app/werewolf/lib/roomSocket";
import { abilityIcon, animalFor, PHASE_INFO } from "../../app/werewolf/lib/theme";
import type { ChatMessage } from "../../app/werewolf/lib/types";
import { makeGame, makeRoom, member, META, VILLAGER, WOLF } from "./helpers";

const err = (status: number, detail?: unknown) =>
  new ApiError(status, typeof detail === "string" ? detail : `Request failed (${status})`, detail === undefined ? undefined : { detail });

describe("errorText", () => {
  it("shows the server's Vietnamese detail for rule errors", () => {
    expect(errorText(err(400, "Chưa tới lượt"))).toBe("Chưa tới lượt");
    expect(errorText(err(409, "Phòng đã đầy"))).toBe("Phòng đã đầy");
    expect(errorText(err(422, "Cần ít nhất 1 Sói"))).toBe("Cần ít nhất 1 Sói");
  });

  it("uses fixed wording for 401, 429 and 503 whatever the detail", () => {
    expect(errorText(err(401, "Not authenticated"))).toBe("Bạn cần đăng nhập lại.");
    expect(errorText(err(429, "Too many"))).toBe("Bạn thao tác quá nhanh, hãy chờ một chút.");
    expect(errorText(err(503, "full"))).toBe("Máy chủ đang đầy phòng, thử lại sau.");
  });

  it("maps the origin refusal", () => {
    expect(errorText(err(403, "Origin not allowed"))).toBe("Nguồn truy cập không được phép.");
  });

  it("falls back per status when there is no string detail", () => {
    expect(errorText(err(400))).toBe("Hành động không hợp lệ lúc này.");
    expect(errorText(err(403))).toBe("Bạn không có quyền làm việc này.");
    expect(errorText(err(404))).toBe("Không tìm thấy phòng.");
    expect(errorText(err(409))).toBe("Phòng không ở trạng thái phù hợp.");
    expect(errorText(new ApiError(422, "x", { detail: [{ msg: "bad" }] }))).toBe("Dữ liệu chưa hợp lệ, hãy kiểm tra lại.");
    expect(errorText(err(500))).toBe("Có lỗi xảy ra.");
  });

  it("maps network failures and unknown values", () => {
    expect(errorText(new TypeError("Failed to fetch"))).toBe("Không kết nối được máy chủ. Hãy thử lại.");
    expect(errorText("boom")).toBe("Có lỗi xảy ra.");
  });

  it("maps websocket error frames", () => {
    expect(frameErrorText("Invalid message")).toBe("Tin nhắn không hợp lệ.");
    expect(frameErrorText("Chưa tới lượt")).toBe("Chưa tới lượt");
    expect(frameErrorText("")).toBe("Có lỗi xảy ra.");
  });
});

describe("socket helpers", () => {
  it("builds the same-origin websocket url", () => {
    expect(socketUrl("ABCDE", { protocol: "https:", host: "x.test" })).toBe("wss://x.test/api/werewolf/ws/ABCDE");
    expect(socketUrl("ABCDE", { protocol: "http:", host: "localhost:3000" })).toBe("ws://localhost:3000/api/werewolf/ws/ABCDE");
    expect(socketUrl("ABCDE")).toBe("ws://localhost:3000/api/werewolf/ws/ABCDE");
  });

  it("backs off exponentially up to the cap", () => {
    expect([0, 1, 2, 3].map(retryDelay)).toEqual([1000, 2000, 4000, 8000]);
    expect(retryDelay(10)).toBe(MAX_RETRY_DELAY_MS);
    expect(retryDelay(-3)).toBe(1000);
  });

  it("parses well-formed frames only", () => {
    const state = makeRoom();
    expect(parseFrame(JSON.stringify({ type: "state", state }))?.type).toBe("state");
    const chat: ChatMessage = { seq: 1, round: "Ngày 1", channel: "public", text: "hi", target: 0, dead: false, author: { id: 2, name: "B" } };
    expect(parseFrame(JSON.stringify({ type: "chat", message: chat }))).toEqual({ type: "chat", message: chat });
    expect(parseFrame(JSON.stringify({ type: "error", error: "Sai" }))).toEqual({ type: "error", error: "Sai" });
  });

  it("ignores malformed frames", () => {
    expect(parseFrame(42)).toBeNull();
    expect(parseFrame("not json")).toBeNull();
    expect(parseFrame("123")).toBeNull();
    expect(parseFrame(JSON.stringify({ type: "state", state: {} }))).toBeNull();
    expect(parseFrame(JSON.stringify({ type: "chat", message: { text: "x" } }))).toBeNull();
    expect(parseFrame(JSON.stringify({ type: "error", error: 4 }))).toBeNull();
    expect(parseFrame(JSON.stringify({ type: "other" }))).toBeNull();
  });

  it("never keeps another member's role in the lobby, even if the server sent it", () => {
    const leaky = makeRoom({
      members: [
        member(1, "alice", { faction: WOLF, ability: { code: "KILL", label: "Giết" } }),
        member(2, "Bình", { faction: VILLAGER, ability: { code: "NONE", label: "x" } }),
      ],
    });
    const clean = sanitizeRoom(leaky);
    expect(clean.members[0].faction).toEqual(WOLF);
    expect(clean.members[1].faction).toBeNull();
    expect(clean.members[1].ability).toBeNull();
    const parsed = parseFrame(JSON.stringify({ type: "state", state: leaky }));
    expect(parsed?.type === "state" && parsed.state.members[1].faction).toBeNull();
  });

  it("leaves a running game untouched", () => {
    const running = makeRoom({ game: makeGame(), started: true });
    expect(sanitizeRoom(running)).toBe(running);
  });

  const msg = (seq: number): ChatMessage => ({ seq, round: "Ngày 1", channel: "public", text: `m${seq}`, target: 0, dead: false, author: { id: 2, name: "B" } });
});

describe("log and theme", () => {
  it("groups by round, newest group first, lines in order", () => {
    const groups = groupLog([
      { round: "Đêm 1", text: "a" },
      { round: "Đêm 1", text: "b" },
      { round: "Ngày 1", text: "c" },
    ]);
    expect(groups).toEqual([
      { round: "Ngày 1", lines: ["c"] },
      { round: "Đêm 1", lines: ["a", "b"] },
    ]);
  });

  it("keeps only the latest 12 rounds", () => {
    const log = Array.from({ length: 20 }, (_, i) => ({ round: `Đêm ${i}`, text: "x" }));
    expect(groupLog(log)).toHaveLength(12);
  });

  it("has icons, a stable animal per name and phase titles", () => {
    expect(abilityIcon("KILL")).toBe("🗡️");
    expect(abilityIcon("???")).toBe("❔");
    expect(animalFor("An")).toBe(animalFor("An"));
    expect(PHASE_INFO.night.title(2)).toBe("Đêm 2");
    expect(PHASE_INFO.day.title(3)).toBe("Ngày 3");
    expect(PHASE_INFO.revenge.title(1)).toBe("Kéo theo!");
    expect(PHASE_INFO.settle.title(1)).toBe("…");
    expect(PHASE_INFO.over.title(1)).toBe("Kết thúc");
  });
});
